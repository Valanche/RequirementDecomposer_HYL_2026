# -*- coding: utf-8 -*-

import json
import logging
import os
import asyncio
from typing import List, Dict, Optional
import textwrap

import openai
from dotenv import load_dotenv
import utils

# --- 初始化 ---
# 从 .env 文件加载环境变量 (OPENAI_API_KEY, etc.)
load_dotenv()

logger = logging.getLogger("evaluater.consistency")

max_retry = 3

# --- 常量定义 ---
CONSISTENCY_EVALUATION_JSON_SCHEMA = textwrap.dedent("""
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
    },
    "instruction": {
      "type": "string",
      "description": "针对当前拆分结果的修改意见"
    }
  },
  "required": ["score", "justification", "instruction"]
}
""")

CONSISTENCY_EVALUATION_SYSTEM_PROMPT = textwrap.dedent(f"""
    你是一个软件工程和需求分析的顶级专家，对于需求的一致性非常严格，但是对于需求场景与需求价值的表述相对宽松
    你的任务是评估一组已分解的需求与原始需求之间的一致性，并给出针对性的修改意见。
    你必须严格按照以下 JSON Schema 结构来构建你的输出。你的响应必须是一个完全符合此结构定义的单一JSON对象。

    ```json
    {CONSISTENCY_EVALUATION_JSON_SCHEMA}
    ```
""")

CONSISTENCY_EVALUATION_USER_PROMPT_TEMPLATE = textwrap.dedent("""
    根据以下标准，严格评估原始需求和已分解的子需求之间的一致性。子需求之间的一致性不需要考虑。
    对于拆解结果中的错误，你需要给出针对性的修改意见，使根据意见重新分解后的需求能获得更高的评分。
    修改意见应针对性的要求避免当前结果中出现的错误，格式如“不准出现……必须包含……”。修改意见也不允许要求增添原始需求中没有的内容。
    **评估维度：一致性**
    {consistency_rules}

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

FEASIBILITY_EVALUATION_JSON_SCHEMA = textwrap.dedent("""
{
  "type": "object",
  "properties": {
    "scores": {
        "properties": {
            "granularity": {
                "type": "integer",
                "description": "粒度评分：1-跨多个模块 2-偏大 3-适中 4-基本原子 5-原子功能"
                "minimum": 1,
                "maximum": 5
            },
            "cohesion": {
                "type": "integer",
                "description": "内聚评分：1-无内聚 2-混合多个目标 3-基本内聚 4-较好内聚 5-高度内聚"
                "minimum": 1,
                "maximum": 5
            },
            "coupling": {
                "type": "integer",
                "description": "耦合评分：1-极高耦合 2-高耦合 3-中等耦合 4-较低耦合 5-低耦合"
                "minimum": 1,
                "maximum": 5
            }
        },
        "required": ["granularity", "cohesion", "coupling"],
    },
    "justification": {
      "type": "string",
      "description": "针对评分的简要说明。"
    },
    "instruction": {
      "type": "string",
      "description": "针对当前子需求的修改意见"
    }
  },
  "required": ["scores", "justification", "instruction"]
}
""")

FEASIBILITY_EVALUATION_SYSTEM_PROMPT = textwrap.dedent(f"""
    你是一个软件工程和需求分析的顶级专家，有着丰富的软件工程经验，善于评估需求的可实现性。
    你的任务是评估一个需求的可实现性，判断其是否需要被进一步分解，并给出针对性的分解意见。
    你必须严格按照以下 JSON Schema 结构来构建你的输出。你的响应必须是一个完全符合此结构定义的单一JSON对象。

    ```json
    {FEASIBILITY_EVALUATION_JSON_SCHEMA}
    ```
""")

FEASIBILITY_EVALUATION_USER_PROMPT_TEMPLATE = textwrap.dedent("""
    根据以下标准，评估需求的可实现性，并给出1-5分的评分。
    对于需求中不符合可实现性评估规则的部分，你需要给出针对性的意见，使根据意见进一步分解后的需求能获得更高的评分。
    修改意见不允许要求增添原始需求中没有的内容。
    ## 评估维度

    ### 1. 粒度（需求拆分的大小是否合适）
    - 5分：需求是单一模块的原子功能，不可再分且无冗余，恰好对应一个完整的业务操作
    - 4分：需求基本是原子功能，但包含少量可分离的次要操作，拆分后可能增加理解成本
    - 3分：适中，含2-3个紧密相关功能
    - 2分：偏大，包含多个可独立模块
    - 1分：过大，跨多个模块

    ### 2. 内聚（需求内部功能的相关性）
    - 5分：高度内聚，所有功能点都服务于同一个业务目标，缺一不可且无无关内容
    - 4分：较好内聚，但存在少量服务于次要目标的辅助操作
    - 3分：基本内聚，包含1-2个与其他功能关联较弱的功能点
    - 2分：内聚不足，包含服务于不同业务目标的混合内容
    - 1分：无内聚，功能杂乱

    ### 3. 耦合（需求对外部依赖的程度）
    - 5分：低耦合，可独立实现和测试，仅依赖标准库或明确的外部接口，无隐式依赖
    - 4分：较低耦合，有少量明确的外部依赖，但可通过Mock方式独立开发和测试
    - 3分：中等耦合，依赖1-2个外部模块的完成，需按顺序开发或提供详细接口定义
    - 2分：高耦合，与多个外部模块存在强耦合，并行开发困难，需频繁联调
    - 1分：极高耦合，无法独立实现，必须与其他需求捆绑交付

    ## 原始需求
    {original_requirement}


    请以指定的JSON格式提供你的评估。
""")


async def _call_llm_api(system_prompt: str, user_prompt: str) -> Optional[str]:
    """
    异步调用OpenAI聊天模型API。
    """
    api_key = os.getenv("OPENAI_API_KEY_CONSISTENCY")
    if not api_key:
        logger.error("未找到OPENAI_API_KEY_CONSISTENCY环境变量。请确保在.env文件中或环境中已设置。")
        return None

    try:
        base_url = os.getenv("OPENAI_BASE_URL_CONSISTENCY") or None
        client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
        model_name = os.getenv("OPENAI_MODEL_NAME_CONSISTENCY", "qwen-plus")

        logger.info(f"正在调用评估模型 (模型: {model_name})，请稍候...")

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
        logger.error(f"OpenAI API请求失败：无法连接到服务器。 {e.__cause__}")
    except openai.RateLimitError:
        logger.error(f"OpenAI API请求因速率限制而被拒绝。")
    except openai.AuthenticationError:
        logger.error(f"OpenAI API请求认证失败，请检查您的API密钥。")
    except openai.APIStatusError as e:
        logger.error(f"OpenAI API返回了非200的状态码：{e.status_code} - {e.response}")
    except Exception as e:
        logger.error(f"调用API时发生未知错误: {e}")
        
    return None

def _build_consistency_evaluation_user_prompt(
    original_requirement: str,
    evaluation_rules: List[str],
    decomposed_requirements: List[Dict]
) -> str:
    """
    构建用于评估的用户提示。
    """
    decomposed_text = "\n".join([f"- {item['description']}" for item in decomposed_requirements])
    

    prompt = CONSISTENCY_EVALUATION_USER_PROMPT_TEMPLATE.format(
        consistency_rules= "\n".join([f"- {item}" for item in evaluation_rules]),
        original_requirement=original_requirement,
        decomposed_requirements=decomposed_text
    )
    return prompt

async def evaluate_consistency(
    rules: List[str],
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
    system_prompt = CONSISTENCY_EVALUATION_SYSTEM_PROMPT

    user_prompt = _build_consistency_evaluation_user_prompt(original_requirement, rules, decomposed_requirements)

    llm_response_str = await _call_llm_api(system_prompt, user_prompt)

    if not llm_response_str:
        return None

    try:
        evaluation_result = json.loads(llm_response_str)
        consistency_score = evaluation_result["score"]
        logger.info(f"一致性评估分数为{consistency_score}")
        return evaluation_result
    except json.JSONDecodeError as e:
        logger.error(f"解析评估结果时发生JSON错误: {e}")
        logger.error(f"原始响应内容: {llm_response_str}")
        return None
    
def _build_feasibility_evaluation_user_prompt(
    original_requirement: str,
    evaluation_rules: List[str],
) -> str:
    """
    构建用于评估的用户提示。
    """
    prompt = FEASIBILITY_EVALUATION_USER_PROMPT_TEMPLATE.format(
        original_requirement=original_requirement
    )
    return prompt

async def evaluate_feasibility(
    rules: List[str],
    decomposed_requirement: str
) -> Optional[Dict]:
    """
    调用LLM评估子需求的可实现性（粒度、内聚、耦合）。

    Args:
        rules (List[str]): 可实现性评估规则
        decomposed_requirement (str): 待评估的子需求。

    Returns:
        Optional[Dict]: LLM返回的评估结果（JSON对象）。
        - score:{granularity,cohesion,coupling},
        - justification
        - instruction
    """
    system_prompt = FEASIBILITY_EVALUATION_SYSTEM_PROMPT

    user_prompt = _build_feasibility_evaluation_user_prompt(decomposed_requirement, rules)

    llm_response_str = await _call_llm_api(system_prompt, user_prompt)

    if not llm_response_str:
        return None

    try:
        evaluation_result = json.loads(llm_response_str)
        all_scores = evaluation_result["scores"]
        
        granualrity_score = all_scores["granularity"]
        cohesion_score = all_scores["cohesion"]
        coupling_score = all_scores["coupling"]
        
        logger.info(f"可实现性评估分数为：粒度{granualrity_score}；内聚{cohesion_score}；耦合{coupling_score}；")
        return evaluation_result
    except json.JSONDecodeError as e:
        logger.error(f"解析评估结果时发生JSON错误: {e}")
        logger.error(f"原始响应内容: {llm_response_str}")
        return None

def load_decomposed_results(file_path: str) -> Optional[List[Dict]]:
    """从JSON文件加载分解结果。"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            print(f"--- [INFO] ---")
            print(f"从 '{file_path}' 加载分解结果...")
            return json.load(f)
    except FileNotFoundError:
        print(f"分解结果文件未找到: {file_path}")
        return None
    except json.JSONDecodeError:
        print(f"解析分解结果文件时出错: {file_path}")
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
                print(f"JSON文件 '{file_path}' 格式不符合预期。")
                return None
    except FileNotFoundError:
        print(f"JSON文件未找到: {file_path}")
        return None
    except json.JSONDecodeError as e:
        print(f"解析JSON文件时发生错误: {file_path} - {e}")
        return None

async def main():

    origin_reqs_file = 'ar_23/data.json'
    decompose_reqs_file = 'ar_23/decomposed_output_6.json'
    evaluation_results_file = 'ar_23/evaluation_output_6.json'

    # 1. 加载原始需求和分解结果
    original_reqs_map = load_original_requirements_from_json(origin_reqs_file)
    decomposed_data = load_decomposed_results(decompose_reqs_file)

    if not original_reqs_map or not decomposed_data:
        logger.error("加载数据失败，终止评估。")
        return

    all_evaluations = []
    score_sum = 0

    # 2. 迭代处理每个分解结果
    for result_item in decomposed_data:
        row_num = result_item.get("row_number")
        decomposed_list = result_item.get("decomposed_list")
        rules = utils.load_active_rules_from_json("rules/consistency.json")

        if not row_num or not decomposed_list:
            logger.warning(f"[WARNING] 跳过无效的分解结果项: {result_item}")
            continue

        original_req = original_reqs_map.get(row_num)

        if not original_req:
            logger.warning(f"[WARNING] 未能为第 {row_num} 行找到对应的原始需求，跳过评估。")
            continue
        
        logger.info(f"正在评估第 {row_num} 行的分解结果...")
        
        # 3. 执行评估
        evaluation = await evaluate_consistency(
            rules=rules,
            original_requirement=original_req,
            decomposed_requirements=decomposed_list
        )

        if evaluation:
            all_evaluations.append({
                "row_number": row_num,
                "evaluation": evaluation
            })
            score_sum += evaluation["score"]
        else:
            logger.warning(f"未能为第 {row_num} 行获取评估结果。")

    # 4. 显示所有评估结果
    if all_evaluations:
        avg_score = score_sum / len(all_evaluations)
        all_evaluations.append({"avg_score": avg_score})
        print(json.dumps(all_evaluations, indent=2, ensure_ascii=False))
        # Optionally, save to a file
        with open(evaluation_results_file, 'w', encoding='utf-8') as f:
            json.dump(all_evaluations, f, indent=2, ensure_ascii=False)
        logger.info(f"评估结果已保存到 {evaluation_results_file}")
    else:
        logger.warning("\n没有生成任何评估结果。")


if __name__ == "__main__":
    asyncio.run(main())
