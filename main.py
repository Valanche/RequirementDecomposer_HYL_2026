import asyncio
import logging
from typing import Tuple, Any, Dict, List, Optional

import utils
from models.supplement_req import SupplementResult
from refiner import DemandSupplementer
import requirement_decomposer
import evaluater



logger_loop = logging.getLogger("loop")
logger_supplement = logging.getLogger("loop.supplement")
logger_loop_consistency = logging.getLogger("loop.consistency")
logger_loop_feasibility = logging.getLogger("loop.feasibility")


max_retry = 3

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    filename='app.log',  # 输出到文件
    filemode='a',  # 'a'表示追加，'w'表示覆盖
    encoding='utf-8'
)

def display_supplement_result(supplement_result, iteration: int, max_iterations: int):
    """在控制台展示补充结果，供用户审核"""
    print("\n" + "=" * 80)
    print(f"需求补充结果 - 第 {iteration}/{max_iterations} 轮")
    print("=" * 80)
    
    
    demand = supplement_result.supplemented_demand
    
    print(f"\n【需求价值】\n{demand.demand_value}")
    print(f"\n【需求场景】\n{demand.demand_scenario}")
    print(f"\n【需求描述】\n{demand.demand_description}")
    print(f"\n【目标用户】\n{demand.target_users}")
    print(f"\n【限制约束】\n{demand.constraints}")
    print(f"\n【外部依赖】\n{demand.external_dependencies}")
    print(f"\n【性能指标】\n{demand.performance_metrics}")
    print(f"\n【ROM&RAM】\n{demand.rom_ram}")
    print(f"\n【验收标准】\n{demand.acceptance_criteria}")
    print(f"\n【验收设备】\n{demand.acceptance_devices}")
    print(f"\n【使用产品差异分析】\n{demand.product_difference_analysis}")
    print(f"\n【2D生态】\n{demand.ecosystem_impact}")
    
    # 输出补充要点
    print("\n" + "=" * 80)
    print("【补充的关键要点】")
    print("=" * 80)
    for i, point in enumerate(supplement_result.key_points_added, 1):
        print(f"{i}. {point}")
    
    # 输出补充依据
    print("\n" + "=" * 80)
    print("【补充依据】")
    print("=" * 80)
    for i, evidence in enumerate(supplement_result.evidence, 1):
        print(f"{i}. {evidence}")
    
    # 输出置信度和待确认问题
    print(f"\n【置信度】: {supplement_result.confidence_score:.2%}")
    
    if supplement_result.questions_for_user:
        print("\n【需要确认的问题】")
        for i, question in enumerate(supplement_result.questions_for_user, 1):
            print(f"{i}. {question}")
    

def get_user_feedback() -> Tuple[bool, Optional[str]]:
    """
    获取用户反馈
    
    Returns:
        Tuple[bool, Optional[str]]: (是否满意, 反馈意见)
        - (True, None): 用户满意
        - (False, feedback): 用户不满意，提供反馈
        - (False, None): 用户取消
    """
    print("\n请审核以上需求补充结果：")
    print("  1. 满意，继续进入需求分解")
    print("  2. 不满意，提供修改意见")
    print("  3. 取消当前需求处理")
    
    while True:
        choice = input("请选择 (1/2/3): ").strip()
        
        if choice == '1':
            return True, None
        elif choice == '2':
            feedback = input("请输入修改意见: ").strip()
            if feedback:
                return False, feedback
            else:
                print("修改意见不能为空，请重新输入")
        elif choice == '3':
            return False, None
        else:
            print("无效输入，请重新选择")


async def supplement_with_feedback_loop(
    supplementer: DemandSupplementer,
    original_request: str,
    file_paths: List[str],
    max_iterations: int = 3
) -> Tuple[Optional[SupplementResult], Optional[str]]:
    """
    带用户反馈循环的需求补充
    
    Returns:
        Tuple[Optional[Any], Optional[str]]: (补充结果, 错误信息)
        - 成功: (SupplementResult, None)
        - 用户取消: (None, "cancelled")
        - 失败: (None, error_message)
    """
    
    current_demand = original_request
    current_feedback = None
    supplement_result = None
    doc_content = None
    
    for iteration in range(1, max_iterations + 1):
        print(f"\n{'='*60}")
        print(f"需求补充 - 第 {iteration}/{max_iterations} 轮")
        print(f"{'='*60}")
        
        if current_feedback:
            logger_supplement.info(f"上一轮反馈意见: {current_feedback}")
        
        try:
            # 加载文档内容
            if doc_content is None:
                doc_content = supplementer.document_loader.load_multiple_documents(file_paths)
            
            # 调用补充接口，传入反馈
            supplement_result = supplementer.supplement_demand(
                original_request=current_demand,
                doc_content=doc_content,
                user_feedback=current_feedback
            )
            
            # 展示结果
            display_supplement_result(supplement_result, iteration, max_iterations)
            
            # 获取用户反馈
            is_satisfied, feedback = get_user_feedback()
            
            if is_satisfied:
                logger_supplement.info(f"用户满意，结束补充，共 {iteration} 轮")
                return supplement_result, None
            
            if feedback is None:  # 用户选择取消
                logger_supplement.info(f"用户取消需求处理")
                return None, "cancelled"
            
            # 更新反馈，进入下一轮
            current_demand = supplement_result.supplemented_demand.to_ar_format()
            new_questions = "\n".join(supplement_result.questions_for_user)
            current_feedback = "上一轮提出的问题:\n" + new_questions + "\n" + "用户整体反馈:\n" + feedback
            
        except Exception as e:
            logger_supplement.error(f"需求补充失败: {e}")
            return None, str(e)
    
    # 达到最大迭代次数
    logger_supplement.info(f"\n⚠️ 已达到最大迭代次数 ({max_iterations})，使用最后一版结果")
    return supplement_result, None

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

    req_source = 'test/test_data/req_inventory2009_sub1.json'
    all_original_requirements = utils.load_requirements_from_json(req_source, limit=None)

    supplementer = DemandSupplementer()
    supplement_files = [
        "req/2009 - inventory 2.0.pdf"
    ]

    res_file = 'test/test_results/supplemented_loop_inventory.json'

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

        SUPPLEMENT_MAX_ITERATIONS = 3

        supplement_result, error = await supplement_with_feedback_loop(
            supplementer=supplementer,
            original_request=main_requirement,
            file_paths=supplement_files,  # 你需要定义的文档路径列表
            max_iterations=SUPPLEMENT_MAX_ITERATIONS
        )
        print("结束补充，进入需求分解")
        
        # 处理补充结果
        if error == "cancelled":
            print(f"\n[跳过] 用户取消处理第 {row_num} 行需求")
            # 保存取消记录后 continue
            continue
        
        if supplement_result is None:
            print(f"\n[ERROR] 第 {row_num} 行需求补充失败: {error}")
            # 保存失败记录后 continue
            continue
        
        supplemented_requirement_text = supplement_result.supplemented_demand.to_ar_format()
        logger_loop.info(f"补充后需求为{supplemented_requirement_text}")
                

        decomposition_result = await consistency_and_feasibility_loop(
            supplemented_requirement_text,
            decomposition_rules,
            consistency_rules,
            None,
            None,
            3
        )

        supplement_dict = supplement_result.model_dump()

        # 3. 处理结果
        if decomposition_result:

            all_decomposed_results.append({
                "row_number": row_num,
                "original_requirement": main_requirement,
                "supplemented": {
                    "supplemented_demand": supplement_dict.get("supplemented_demand"),
                    "key_points_added": supplement_dict.get("key_points_added", []),
                    "evidence": supplement_dict.get("evidence", []),
                    "confidence_score": supplement_dict.get("confidence_score"),
                    "questions_for_user": supplement_dict.get("questions_for_user", [])
                },
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


    




        

