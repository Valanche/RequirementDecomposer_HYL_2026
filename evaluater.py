# -*- coding: utf-8 -*-

import json
import os
import asyncio
from typing import List, Dict, Optional
import textwrap

import openai
from dotenv import load_dotenv

# --- 初始化 ---
# 从 .env 文件加载环境变量 (OPENAI_API_KEY, etc.)
load_dotenv()

# --- 常量定义 ---
EVALUATION_JSON_SCHEMA = textwrap.dedent("""
{
  "type": "object",
  "properties": {
    "score": {
      "type": "integer",
      "description": "一致性评分，范围从1到5。",
      "minimum": 1,
      "maximum": 5
    },
    "justification": {
      "type": "string",
      "description": "针对评分的简要说明。"
    }
  },
  "required": ["score", "justification"]
}
""")

EVALUATION_SYSTEM_PROMPT = textwrap.dedent(f"""
    你是一个软件工程和需求分析的顶级专家，对于需求的一致性非常严格。
    你的任务是评估一个已分解的需求与原始需求之间的一致性。
    你必须严格按照以下 JSON Schema 结构来构建你的输出。你的响应必须是一个完全符合此结构定义的单一JSON对象。

    ```json
    {EVALUATION_JSON_SCHEMA}
    ```
""")

EVALUATION_USER_PROMPT_TEMPLATE = textwrap.dedent("""
    根据以下标准，严格评估原始需求和已分解的子需求之间的一致性。

    **评估维度：一致性**
    - 已分解的子需求必须完全涵盖原始需求的所有内容。
    - 已分解的子需求不得超出原始需求的功能范围。
    - 已分解的子需求不得改变原始需求的实现技术，也不得使用原始需求中没有的技术。
    - 已分解的子需求不得对原始需求进行细化，必须完全忠实于原始需求的内容。

    **评分标准：**
    - 1 (强烈不同意): 拆解结果与预期标准严重不符，缺失原始需求的大部分内容或包含大量超出范围的功能。
    - 2 (不同意): 拆解结果与预期标准不符，存在重大缺陷或不符合项。
    - 3 (中立): 拆解结果符合预期标准，但对原始需求进行了细化，出现了原始需求没有的内容。
    - 4 (同意): 拆解结果普遍符合或略高于预期标准，只有少量需要改进的地方。
    - 5 (强烈同意): 拆解结果优秀，完全符合或超出预期标准。

    **原始需求：**
    {original_requirement}

    **已分解的子需求：**
    {decomposed_requirements}

    请以指定的JSON格式提供你的评估。
""")


async def _call_llm_api(system_prompt: str, user_prompt: str) -> Optional[str]:
    """
    异步调用OpenAI聊天模型API。
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("[ERROR] 未找到OPENAI_API_KEY环境变量。请确保在.env文件中或环境中已设置。")
        return None

    try:
        base_url = os.getenv("OPENAI_BASE_URL") or None
        client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
        model_name = os.getenv("OPENAI_MODEL_NAME", "qwen-plus")

        print(f"--- [INFO] ---")
        print(f"正在调用评估模型 (模型: {model_name})，请稍候...")

        response = await client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"}
        )
        
        print("--- [INFO] ---")
        print("API调用成功。")
        
        return response.choices[0].message.content

    except openai.APIConnectionError as e:
        print(f"[ERROR] OpenAI API请求失败：无法连接到服务器。 {e.__cause__}")
    except openai.RateLimitError:
        print(f"[ERROR] OpenAI API请求因速率限制而被拒绝。")
    except openai.AuthenticationError:
        print(f"[ERROR] OpenAI API请求认证失败，请检查您的API密钥。")
    except openai.APIStatusError as e:
        print(f"[ERROR] OpenAI API返回了非200的状态码：{e.status_code} - {e.response}")
    except Exception as e:
        print(f"[ERROR] 调用API时发生未知错误: {e}")
        
    return None

def _build_evaluation_user_prompt(
    original_requirement: str,
    decomposed_requirements: List[Dict]
) -> str:
    """
    构建用于评估的用户提示。
    """
    decomposed_text = "\n".join([f"- {item['description']}" for item in decomposed_requirements])
    
    prompt = EVALUATION_USER_PROMPT_TEMPLATE.format(
        original_requirement=original_requirement,
        decomposed_requirements=decomposed_text
    )
    return prompt

async def evaluate_decomposition(
    original_requirement: str,
    decomposed_requirements: List[Dict]
) -> Optional[Dict]:
    """
    调用LLM评估需求分解的质量。

    Args:
        original_requirement (str): 原始需求文本。
        decomposed_requirements (List[Dict]): 分解后的子需求列表。

    Returns:
        Optional[Dict]: LLM返回的评估结果（JSON对象）。
    """
    system_prompt = EVALUATION_SYSTEM_PROMPT
    user_prompt = _build_evaluation_user_prompt(original_requirement, decomposed_requirements)

    llm_response_str = await _call_llm_api(system_prompt, user_prompt)

    if not llm_response_str:
        return None

    try:
        evaluation_result = json.loads(llm_response_str)
        return evaluation_result
    except json.JSONDecodeError as e:
        print(f"[ERROR] 解析评估结果时发生JSON错误: {e}")
        print(f"原始响应内容: {llm_response_str}")
        return None

def load_decomposed_results(file_path: str) -> Optional[List[Dict]]:
    """从JSON文件加载分解结果。"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            print(f"--- [INFO] ---")
            print(f"从 '{file_path}' 加载分解结果...")
            return json.load(f)
    except FileNotFoundError:
        print(f"[ERROR] 分解结果文件未找到: {file_path}")
        return None
    except json.JSONDecodeError:
        print(f"[ERROR] 解析分解结果文件时出错: {file_path}")
        return None

def load_original_requirements_from_json(file_path: str) -> Optional[Dict[int, str]]:
    """
    从JSON文件中加载原始需求，并以row为键存入字典。

    Args:
        file_path (str): JSON文件的路径。

    Returns:
        Optional[Dict[int, str]]: 以row number为键，需求文本为值的字典。
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, list) and all(isinstance(item, dict) and 'row' in item and 'req' in item for item in data):
                req_map = {item['row']: item['req'] for item in data}
                print(f"--- [INFO] ---")
                print(f"成功从 '{file_path}' 中读取 {len(req_map)} 条原始需求并构建映射。")
                return req_map
            else:
                print(f"[ERROR] JSON文件 '{file_path}' 格式不符合预期。")
                return None
    except FileNotFoundError:
        print(f"[ERROR] JSON文件未找到: {file_path}")
        return None
    except json.JSONDecodeError as e:
        print(f"[ERROR] 解析JSON文件时发生错误: {file_path} - {e}")
        return None

async def main():
    """主执行函数"""
    print("开始执行评估流程...")

    # 1. 加载原始需求和分解结果
    original_reqs_map = load_original_requirements_from_json('ar_23/data.json')
    decomposed_data = load_decomposed_results('ar_23/decomposed_output.json')

    if not original_reqs_map or not decomposed_data:
        print("[ERROR] 加载数据失败，终止评估。")
        return

    all_evaluations = []

    # 2. 迭代处理每个分解结果
    for result_item in decomposed_data:
        row_num = result_item.get("row_number")
        decomposed_list = result_item.get("decomposed_list")

        if not row_num or not decomposed_list:
            print(f"[WARNING] 跳过无效的分解结果项: {result_item}")
            continue

        original_req = original_reqs_map.get(row_num)

        if not original_req:
            print(f"[WARNING] 未能为第 {row_num} 行找到对应的原始需求，跳过评估。")
            continue
        
        print(f"\n" + "#"*50)
        print(f"正在评估第 {row_num} 行的分解结果...")
        
        # 3. 执行评估
        evaluation = await evaluate_decomposition(
            original_requirement=original_req,
            decomposed_requirements=decomposed_list
        )

        if evaluation:
            all_evaluations.append({
                "row_number": row_num,
                "evaluation": evaluation
            })
            print(f"第 {row_num} 行评估完成。")
        else:
            print(f"未能为第 {row_num} 行获取评估结果。")

    # 4. 显示所有评估结果
    if all_evaluations:
        print("\n" + "="*60)
        print("所有评估已完成！最终结果如下：")
        print(json.dumps(all_evaluations, indent=2, ensure_ascii=False))
        print("="*60)
        # Optionally, save to a file
        with open('ar_23/evaluation_output.json', 'w', encoding='utf-8') as f:
            json.dump(all_evaluations, f, indent=2, ensure_ascii=False)
        print("评估结果已保存到 ar_23/evaluation_output.json")
    else:
        print("\n没有生成任何评估结果。")


if __name__ == "__main__":
    asyncio.run(main())
