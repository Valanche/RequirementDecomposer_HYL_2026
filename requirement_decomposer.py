# -*- coding: utf-8 -*-

import json
import uuid
import os
import asyncio
from typing import List, Dict, Optional
import textwrap

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
        "description": "子需求的唯一标识符 (UUID)。"
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



# --- 核心函数 ---

def load_requirements_from_json(file_path: str, limit: Optional[int] = None) -> Optional[List[Dict]]:
    """
    从JSON文件中加载原始需求列表。

    Args:
        file_path (str): JSON文件的路径。
        limit (Optional[int]): 可选参数，指定读取文件的前多少个需求。

    Returns:
        Optional[List[Dict]]: 包含'row'和'req'的字典列表，或None。
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, list) and all(isinstance(item, dict) and 'row' in item and 'req' in item for item in data):
                if limit is not None and limit > 0:
                    data = data[:limit]
                    print(f"--- [INFO] ---")
                    print(f"成功从 '{file_path}' 中读取前 {len(data)} 条需求。")
                else:
                    print(f"--- [INFO] ---")
                    print(f"成功从 '{file_path}' 中读取 {len(data)} 条需求。")
                return data
            else:
                print(f"[ERROR] JSON文件 '{file_path}' 格式不符合预期，应为包含'row'和'req'字段的字典列表。")
                return None
    except FileNotFoundError:
        print(f"[ERROR] JSON文件未找到: {file_path}")
        return None
    except json.JSONDecodeError as e:
        print(f"[ERROR] 解析JSON文件时发生错误: {file_path} - {e}")
        return None
    except Exception as e:
        print(f"[ERROR] 读取JSON文件时发生未知错误: {e}")
        return None

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
    output_format_instruction: Optional[str]
) -> str:
    prompt_parts = []

    prompt_parts.append("\n=== 分解规则 ===")
    for i, rule in enumerate(rules, 1):
        prompt_parts.append(f"{i}. {rule}")

    prompt_parts.append("\n=== 原始需求 ===")
    prompt_parts.append(original_requirement)

    if output_format_instruction:
        prompt_parts.append("\n=== 额外输出要求 ===")
        prompt_parts.append(output_format_instruction)

    return "\n".join(prompt_parts)


async def _call_llm_api(system_prompt: str, user_prompt: str) -> Optional[str]:
    # ... (此函数内容不变) ...
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("[ERROR] 未找到OPENAI_API_KEY环境变量。请确保在.env文件中或环境中已设置。\n")
        return None

    try:
        base_url = os.getenv("OPENAI_BASE_URL") or None
        # 使用异步客户端
        client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
        
        model_name = os.getenv("OPENAI_MODEL_NAME", "qwen-plus")

        print("--- [INFO] ---")
        print(f"正在调用OpenAI API (模型: {model_name})，请稍候...")

        response = await client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0   
        )
        
        print("--- [INFO] ---")
        print("API调用成功。\n")
        
        return response.choices[0].message.content

    except openai.APIConnectionError as e:
        print(f"[ERROR] OpenAI API请求失败：无法连接到服务器。 {e.__cause__}\n")
    except openai.RateLimitError as e:
        print(f"[ERROR] OpenAI API请求因速率限制而被拒绝。\n")
    except openai.AuthenticationError as e:
        print(f"[ERROR] OpenAI API请求认证失败，请检查您的API密钥。\n")
    except openai.APIStatusError as e:
        print(f"[ERROR] OpenAI API返回了非200的状态码：{e.status_code} - {e.response}\n")
    except Exception as e:
        print(f"[ERROR] 调用API时发生未知错误: {e}\n")
        
    return None


async def decompose_requirement(
    original_requirement: str,
    rules: List[str] = None,
    output_format_instruction: Optional[str] = None,
) -> Optional[List[Dict]]:
    # ... (此函数内容不变) ...
    # 1. 构建提示
    system_prompt = _build_system_prompt()
    user_prompt = _build_user_prompt(original_requirement, rules, output_format_instruction)

    # 2. (真实)调用LLM API
    llm_response_str = await _call_llm_api(system_prompt, user_prompt)

    if not llm_response_str:
        return None

    # 3. 解析结果
    try:
        sub_requirements_list = json.loads(llm_response_str)
        if isinstance(sub_requirements_list, list):
            return sub_requirements_list
        else:
            print(f"[ERROR] LLM返回的不是一个有效的JSON数组: {sub_requirements_list}\n")
            return None
    except json.JSONDecodeError as e:
        print(f"[ERROR] 解析LLM响应时发生JSON错误: {e}\n")
        print(f"原始响应内容: {llm_response_str}\n")
        return None

def save_results_to_json(results: List[Dict], output_path: str):
    """
    将需求列表保存为格式化的JSON文件。

    Args:
        results (List[Dict]): 包含所有行分解结果的列表。
        output_path (str): 输出的JSON文件路径。
    """
    try:
        print("\n" + "=" * 50)
        print(f"步骤 3: 将所有结果保存到JSON文件 '{output_path}'...")
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
            
        print(f"--- [INFO] ---")
        print(f"结果已成功保存。")

    except Exception as e:
        print(f"[ERROR] 保存JSON文件时发生未知错误: {e}")

async def main():
    """主执行函数"""
    # 定义分解规则 (这部分在循环外定义，因为它们是固定的)
    decomposition_rules = [
        "子需求应当是能分配给单一功能模块的，不可再分的最小原子功能需求，单个需求的内容不得跨越不同功能模块实现。",
        "子需求只是对原始需求的分解而不是细化，需求描述中不可新增原始需求中没有的内容。",
        "子需求描述的内容必须完全涵盖原始需求描述的所有内容。",
        "子需求的功能集合不得超出原始需求的功能范围。",
        "子需求的需求价值和需求场景应根据原始需求进行拆分，但不得超出原始需求的场景范围",
        "子需求的性能指标和ROMRAM要求应根据原始需求进行拆分，但必须忠实于原始需求的内容，不得新增项目或指标",
        "子需求应严格保持原始需求中的技术细节，包括算法、协议、版本等，不得有任何形式的推断或补充。",
        "原始需求中为“无”等无内容表述的字段，子需求中也保持为“无”等表述"
        # "子需求之间可能存在调用关系，必须通过外部依赖字段明确标注；依赖标注不得影响需求的原子性，仅用于说明调用关系"
        
        
    ]
    format_instruction = None

    req_source = 'ar_23/data_ds1.json'
    res_file = 'ar_23/decomposed_output.json'

    all_decomposed_results = [] # 用于存储所有分解结果的列表

    # 从JSON文件加载所有原始需求
    print("\n" + "=" * 50)
    
    print("步骤 1: 从JSON文件 {} 读取所有主需求...", req_source)
    all_original_requirements = load_requirements_from_json(req_source, limit=None)

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
            output_format_instruction=format_instruction,
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
        save_results_to_json(all_decomposed_results, res_file)
    else:
        print(f"\n没有成功的需求分解结果，未生成 {res_file} 文件。")

if __name__ == "__main__":
    # 使用asyncio运行主异步函数
    asyncio.run(main())

