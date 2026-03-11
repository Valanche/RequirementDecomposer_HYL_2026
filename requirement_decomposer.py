# -*- coding: utf-8 -*-

import json
import logging
import os
import asyncio
from typing import List, Dict, Optional
import textwrap

import utils

# 新增的依赖，需要 pip install openpyxl
try:
    from openpyxl import load_workbook, Workbook
    from openpyxl.utils.exceptions import InvalidFileException
except ImportError:
    print("[ERROR] openpyxl库未安装。请运行 'pip install openpyxl' 进行安装。")
    exit(1)

import openai
from dotenv import load_dotenv

# --- 初始化 ---
# 从 .env 文件加载环境变量 (OPENAI_API_KEY, etc.)

load_dotenv()
logger = logging.getLogger("decomposer")

# --- 常量定义 ---
REQ_FORMAT_CONTENT = textwrap.dedent("""
    【需求价值】
    该需求旨在解决何种核心问题，或为用户及业务带来何种收益。

    【需求场景】
    该需求的适用业务场景与具体触发条件。

    【需求描述】
    该需求需实现功能的详细说明，包括主要流程与关键交互。

    【目标用户】
    该需求的明确使用人群，例如某类终端用户或系统角色。

    【限制约束】
    实现该需求需满足的约束条件，如用户前置操作、技术或业务限制等。

    【外部依赖】
    该需求所依赖的外部系统、组件或服务。

    【性能指标】
    该需求的性能要求，例如响应时间、并发能力等指标，需明确对比基线或提升目标。

    【ROM&RAM】
    该需求对设备存储（ROM）与内存（RAM）的占用要求，需明确对比基线或优化目标。

    【验收标准】
    该需求通过验收的判定条件与依据，例如功能完整性、性能达成度等维度。

    【验收设备】
    验收该需求所需的设备类型与测试环境，如特定型号手机、操作系统版本等。

    【使用产品差异分析】
    该需求在不同设备或平台上的使用行为差异；如无差异，需明确说明。

    【2D生态】
    该需求对面向开发者的软件生态建设可能产生的影响。
""")

JSON_SCHEMA_DEFINITION = textwrap.dedent("""\
{
  "type": "array",
  "description": "分解后的子需求列表。",
  "items": {
    "type": "object",
    "properties": {
      "id": {
        "type": "string",
        "description": "子需求的编号，格式如'req-0001'"
      },
      "description": {
        "type": "string",
        "description": "子需求的详细描述，必须严格遵循'需求格式定义'。"
      }
    },
    "required": ["id", "description"]
  }
}
""")

# --- 核心函数 ---


def _build_system_prompt() -> str:
    return textwrap.dedent(f"""
        你是一个顶级的软件需求工程师。你的任务是根据用户提供的复杂需求、分解规则和格式定义，将需求分解为一系列粒度更小的子需求。在这一过程中，你只负责分解而不负责细化，不允许添加细节。
        你必须以扁平化的列表结构返回结果。

        ## 输出格式
        你必须严格遵循以下需求格式定义和JSON Schema来构造你的输出。你的响应必须是一个**JSON数组**，数组中的每个元素都是一个完整的子需求对象。                 
       
        --- 需求格式定义 ---
        {REQ_FORMAT_CONTENT}
        --- 需求格式定义结束 ---
        --- JSON Schema定义 ---
        ```json
        {JSON_SCHEMA_DEFINITION}
        ```
        --- JSON Schema定义结束 ---
    """)

def _build_user_prompt(
    original_requirement: str,
    rules: List[str],
    specific_instruction: Optional[str]
) -> str:
    prompt_parts = []

    prompt_parts.append("\n=== 分解规则 ===")
    for i, rule in enumerate(rules, 1):
        prompt_parts.append(f"{i}. {rule}")

    prompt_parts.append("\n=== 原始需求 ===")
    prompt_parts.append(original_requirement)

    if specific_instruction:
        prompt_parts.append("\n=== 额外要求 ===")
        prompt_parts.append(specific_instruction)
        logger.info(f"携带额外要求：{specific_instruction}")

    return '\n'.join(prompt_parts)

async def _call_llm_api(system_prompt: str, user_prompt: str) -> Optional[str]:
    api_key = os.getenv("OPENAI_API_KEY_DECOMPOSE")
    if not api_key:
        logger.error("未找到OPENAI_API_KEY_DECOMPOSE环境变量。请确保在.env文件中或环境中已设置。\n")
        return None

    try:
        base_url = os.getenv("OPENAI_BASE_URL_DECOMPOSE") or None
        # 使用异步客户端
        client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
        
        model_name = os.getenv("OPENAI_MODEL_NAME_DECOMPOSE", "qwen-plus")

        logger.info(f"正在调用模型: {model_name})")

        response = await client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0   
        )
        
        return response.choices[0].message.content

    except openai.APIConnectionError as e:
        logger.exception("OpenAI API请求失败：无法连接到服务器。")
    except openai.RateLimitError as e:
        logger.exception("OpenAI API请求因速率限制而被拒绝。")
    except openai.AuthenticationError as e:
        logger.exception("OpenAI API请求认证失败，请检查您的API密钥。")
    except openai.APIStatusError as e:
        logger.exception("OpenAI API返回了非200的状态码：")
    except Exception as e:
        logger.exception("调用API时发生未知错误:")
        
    return None


async def decompose_requirement(
    original_requirement: str,
    rules: List[str],
    specific_instruction: Optional[str] = None,
) -> Optional[List[Dict]]:

    system_prompt = _build_system_prompt()
    user_prompt = _build_user_prompt(original_requirement, rules, specific_instruction)

    llm_response_str = await _call_llm_api(system_prompt, user_prompt)

    if not llm_response_str:
        return None

    try:
        sub_requirements_list = json.loads(llm_response_str)
        if isinstance(sub_requirements_list, list):
            return sub_requirements_list
        else:
            logger.error(f"LLM返回的不是一个有效的JSON数组: {sub_requirements_list}\n")
            return None
    except json.JSONDecodeError as e:
        logger.exception(f"解析LLM响应时发生JSON错误, 原始响应内容: {llm_response_str}")
        return None

async def main():
    """主执行函数"""

    decomposition_rules = utils.load_active_rules_from_json("rules/decomposition.json")
    format_instruction = None

    req_source = 'ar_23/data_ds1.json'
    res_file = 'ar_23/decomposed_output.json'

    all_decomposed_results = [] # 用于存储所有分解结果的列表

    # 从JSON文件加载所有原始需求
    print("\n" + "=" * 50)
    
    print("步骤 1: 从JSON文件 {} 读取所有主需求...", req_source)
    all_original_requirements = utils.load_requirements_from_json(req_source, limit=None)

    if not all_original_requirements:
        print("[ERROR] 未能加载原始需求，终止程序。")
        return

    # 循环处理加载的需求
    for req_item in all_original_requirements:
        row_num = req_item.get("row")
        main_requirement = req_item.get("req")

        if not row_num or not main_requirement:
            print(f"[WARNING] 发现无效的需求项 (row: {row_num}, req: {main_requirement})，跳过。")
            continue

        print("\n" + "#" * 60)
        print(f"开始处理第 {row_num} 行的需求...")
        print("#" * 60)

        # 2. 执行分解
        print("\n" + "=" * 50)
        print("步骤 2: 开始执行需求分解...")
        decomposed_list = await decompose_requirement(
            original_requirement=main_requirement,
            rules=decomposition_rules,
            specific_instruction=format_instruction,
        )

        # 3. 处理结果
        if decomposed_list:
            # 将当前行的分解结果添加到列表中
            all_decomposed_results.append({
                "row_number": row_num,
                "decomposed_list": decomposed_list
            })
            print(f"第 {row_num} 行的需求分解结果已收集。")
        else:
            print(f"\n未能为第 {row_num} 行获取有效的需求分解结果。")

    # 循环结束后，将所有结果保存到一个JSON文件
    if all_decomposed_results:
        # 4a. 保存到JSON文件
        utils.save_results_to_json(all_decomposed_results, res_file)
    else:
        print(f"\n没有成功的需求分解结果，未生成 {res_file} 文件。")

if __name__ == "__main__":
    asyncio.run(main())

