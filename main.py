import asyncio
import logging
from typing import Dict, List, Optional

import utils
import requirement_decomposer
import evaluater


logger_loop = logging.getLogger("loop")
logger_loop_consistency = logging.getLogger("loop.consistency")
logger_loop_feasibility = logging.getLogger("loop.feasibility")


max_retry = 3

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='app.log',  # 输出到文件
    filemode='a',  # 'a'表示追加，'w'表示覆盖
    encoding='utf-8'
)


async def consistency_loop(
    original_requirement: str,
    decomposition_rules: List[str],
    consistency_rules: List[str],
    specific_instruction: Optional[str] = None,
    loops_allowed: Optional[int] = 3
) -> Optional[Dict]:
    """
    对需求进行拆分，检测拆分后需求与原始需求的一致性，并根据意见重新拆分。

    Args:
        loops_allowed (Optional[int] = 3): 允许运行的次数，至少为1

    Returns:
        Optional[Dict]: 子需求集合以及对应的一致性评估结果
        - "result_list": [{id,description},...]
        - "consistency_evaluation": {score,justification,instruction}
    """

    if loops_allowed <= 0:
        logger_loop_consistency.error("循环次数错误")
        return None
    
    for i in range(max_retry):
        decomposed_list = await requirement_decomposer.decompose_requirement(
            original_requirement,
            decomposition_rules,
            specific_instruction,
        )
        if decomposed_list:
            break
    
    for i in range(max_retry):
        evaluation_result = await evaluater.evaluate_consistency(
            consistency_rules, 
            original_requirement,
            decomposed_list
        )
        if evaluation_result:
            break

    cur_score = evaluation_result["score"]
    if cur_score < 5:
        next_instruction = evaluation_result["instruction"]
        if specific_instruction is not None:
            next_instruction = specific_instruction + next_instruction

        next_loop_result = await consistency_loop(
            original_requirement,
            decomposition_rules,
            consistency_rules,
            next_instruction,
            loops_allowed-1
            )
        
        if next_loop_result is not None and next_loop_result["consistency_evaluation"]["score"] >= cur_score:
            logger_loop_consistency.info(f"使用拆分结果{loops_allowed-1}")
            return next_loop_result

    return {
        "result_list": decomposed_list,
        "consistency_evaluation": evaluation_result
    }    

async def feasibility_judge(
    original_requirement: str,
    # decomposition_rules: List[str],
    feasibility_rules: List[str],
    # specific_instruction: Optional[str] = None,
    # loops_allowed: Optional[int] = 3
) -> Optional[Dict]:
    """
    评估拆分后需求的可实现性，并根据意见进一步拆分。

    Args:
        loops_allowed (Optional[int] = 3): 允许运行的次数，至少为1

    Returns:
        Optional[Dict]: 可实现性评估结果，包含是否需要进一步拆分
        - need_decomposition: False,
        - feasibility_evaluation: {score, justification,instruction}
    """

    # if loops_allowed <= 0:
    #     logger_loop_consistency.error("循环次数错误")
    #     return None
    
    for i in range(max_retry):
        evaluation_result = await evaluater.evaluate_feasibility(
            None, 
            original_requirement,
        )
        if evaluation_result:
            break

    all_scores = evaluation_result["scores"]
        
    granualrity_score = all_scores["granularity"]
    cohesion_score = all_scores["cohesion"]
    coupling_score = all_scores["coupling"]

    res = {
        "need_decomposition": False,
        "feasibility_evaluation": evaluation_result
    }   

    if granualrity_score <= 3 or cohesion_score <=3 or coupling_score <=3:
        logger_loop_feasibility.info("分数过低，需要进一步拆分")
        res["need_decomposition"] = True

    return res

async def consistency_and_feasibility_loop(
    input_requirement: str,
    input_decomposition_rules: List[str],
    input_consistency_rules: List[str],
    input_feasibility_rules: List[str],
    specific_instruction: Optional[str] = None,
    depth_allowed: Optional[int] = 3
) -> Optional[Dict]:
    if depth_allowed <= 0:
        logger_loop.info("拆分深度达到限制")
        return None
    
    decomposed_list = await consistency_loop(original_requirement=input_requirement,
                                        decomposition_rules=input_decomposition_rules,
                                        consistency_rules=input_consistency_rules,
                                        loops_allowed=3)

    if decomposed_list:

        sub_reqs = decomposed_list["result_list"]
        
        for sub_req in sub_reqs:
            feasibility_result = await feasibility_judge(sub_req["description"], input_feasibility_rules)
            sub_req["feasibility_evaluation"] = feasibility_result["feasibility_evaluation"]   
            
            if feasibility_result["need_decomposition"] and depth_allowed >= 1:
                feasibility_instruction = feasibility_result["feasibility_evaluation"]["instruction"]
                further_decomnposition = await consistency_and_feasibility_loop(
                                        sub_req["description"],
                                        input_decomposition_rules,
                                        input_consistency_rules,
                                        input_feasibility_rules,
                                        feasibility_instruction,
                                        depth_allowed-1)             
            sub_req["decomposition"] = further_decomnposition
            
    
    return decomposed_list
    

    

async def main():
    decomposition_rules = utils.load_active_rules_from_json("rules/decomposition.json")
    consistency_rules = utils.load_active_rules_from_json("rules/consistency.json")

    req_source = 'ar_23/data_ds1.json'
    all_original_requirements = utils.load_requirements_from_json(req_source, limit=None)

    res_file = 'ar_23/decomposed_output_loop.json'

    all_decomposed_results = [] # 用于存储所有分解结果的列表

    # 循环处理加载的需求
    for req_item in all_original_requirements:
        row_num = req_item.get("row")
        main_requirement = req_item.get("req")

        if not row_num or not main_requirement:
            print(f"[WARNING] 发现无效的需求项 (row: {row_num}, req: {main_requirement})，跳过。")
            continue

        print(f"开始处理第 {row_num} 行的需求...")

        if not all_original_requirements:
                print("[ERROR] 未能加载原始需求，终止程序。")

        decomposition_result = await consistency_and_feasibility_loop(
            main_requirement,
            decomposition_rules,
            consistency_rules,
            None,
            None,
            3
        )

        # 3. 处理结果
        if decomposition_result:

            all_decomposed_results.append({
                "row_number": row_num,
                "original_requirement": main_requirement,
                "decomposition": decomposition_result
            })

            print(f"第 {row_num} 行的需求分解结果已收集。")
        else:
            print(f"\n未能为第 {row_num} 行获取有效的需求分解结果。")

    # 循环结束后，将所有结果保存到一个JSON文件
    if all_decomposed_results:
        utils.save_results_to_json(all_decomposed_results, res_file)
    else:
        print(f"\n没有成功的需求分解结果，未生成 {res_file} 文件。")


if __name__ == "__main__":
    asyncio.run(main())


    




        

