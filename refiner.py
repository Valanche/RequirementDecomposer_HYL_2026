# -*- coding: utf-8 -*-
import asyncio
import json
import logging
import os
import textwrap
from typing import Optional, List, Dict

from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from langchain_openai import ChatOpenAI
from models.supplement_req import SupplementResult
from document_loader import DocumentLoader


load_dotenv()
logger = logging.getLogger("refiner")

# --- LangChain Model and Prompt Definition ---

llm = ChatOpenAI(
    model=os.getenv("OPENAI_MODEL_NAME_REFINE", "gpt-4-turbo"),
    api_key=os.getenv("OPENAI_API_KEY_REFINE") or os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL_REFINE") or os.getenv("OPENAI_BASE_URL"),
    temperature=0
)

schema_file_path = "models/supplement_req.json"
with open(schema_file_path, 'r', encoding='utf-8') as f:
    output_schema = json.load(f)
    
# 转换为格式化的 JSON 字符串
schema_str = json.dumps(output_schema, ensure_ascii=False, indent=2)

JSON_SCHEMA_DEFINITION = schema_str.replace('{', '{{').replace('}', '}}')

REFINEMENT_SYSTEM_PROMPT = textwrap.dedent("""
        你是一个专业的产品需求分析师，擅长从技术文档、需求文档、产品说明中提取关键信息，并将用户不完整的原始需求补充为完整、规范的需求。
        你补充之后的的需求会被交给其他需求工程师进行分解和细化，因此补充的需求应当有尽量完整的上下文信息。

        你的职责：
        1. 深入理解用户提供的文档内容
        2. 识别原始需求中的缺失信息
        3. 从文档中提取相关细节进行补充
        4. 确保补充后的需求结构完整、逻辑清晰，包含完整的上下文信息。

        补充原则：
        - 保持原始需求的核心意图不变
        - 补充的内容必须有文档依据
        - 如果文档中存在矛盾或歧义，明确指出并询问
        - 对于无法从文档中获取的信息，合理推断并标注推断依据
        - 补充要点应具体、可衡量、可验证
""")

def create_refinement_prompt(raw_req: str, docs: str, feedback: Optional[str]) -> ChatPromptTemplate:
    
    human_prompt_template = """
    ## 一、用户原始需求
    {raw_req}

    ## 二、参考文档内容
    {docs}

    ## 三、用户要求
    """
    
    if feedback:
        human_prompt_template += """
        {feedback}
    """
    
    human_prompt_template += f"""
    ## 四、补充要求

    请根据上述文档内容，将原始需求补充为包含充足上下文信息的完整需求,并以json格式输出。

    **特别要求：**
    1. 严格按照指定的 12 个维度（需求价值、需求场景、需求描述、目标用户、限制约束、外部依赖、性能指标、ROM&RAM、验收标准、验收设备、使用产品差异分析、2D生态）进行补充
    2. 每个维度的内容必须基于文档，不能凭空捏造
    3. 如果文档中没有某个维度的信息，请结合需求类型和行业常识进行合理推断，并在补充依据中标注为"推断"
    4. 补充的关键要点要具体，不要泛泛而谈
    5. 补充依据要明确引用文档的具体内容或说明推理逻辑
    6. 对于不确定的内容，放入 questions_for_user 中
    
    **JSON Schema定义：**
    ```json
    {JSON_SCHEMA_DEFINITION}
    ```

    """


    prompt = ChatPromptTemplate.from_messages([
        SystemMessagePromptTemplate.from_template(REFINEMENT_SYSTEM_PROMPT),
        HumanMessagePromptTemplate.from_template(human_prompt_template)
    ])

    return prompt


class DemandSupplementer:
    
    def __init__(self):
        self.llm = llm
        
        self.structured_llm = self.llm.with_structured_output(SupplementResult)

        # 文档加载器映射
        self.document_loader = DocumentLoader()

    
    def supplement_demand(
        self,
        original_request: str,
        doc_content: str,
        user_feedback: Optional[str] = None
    ) -> SupplementResult:
        """
        补充需求
        
        Args:
            original_request: 用户原始需求
            doc_content: 文档内容（可以是单个文档或合并后的多个文档）
            user_feedback: (用户提供的)额外的反馈/上下文信息
        
        Returns:
            SupplementResult: 包含补充后需求、补充要点、依据等
        """
        
        prompt = create_refinement_prompt(original_request, doc_content, user_feedback)
        
        # 执行调用
        chain = prompt | self.structured_llm
        result = chain.invoke(
            {
                "raw_req": original_request,
                "docs": doc_content
            }
        )
        
        return result
    
    def supplement_from_files(
        self,
        original_request: str,
        file_paths: List[str],
        additional_context: Optional[str] = None
    ) -> SupplementResult:
        """从文件加载文档后补充需求"""
        
        # 加载文档
        doc_content = self.document_loader.load_multiple_documents(file_paths)
        
        # 限制文档长度（避免超 token）
        max_chars = 10000
        if len(doc_content) > max_chars:
            doc_content = doc_content[:max_chars] + "\n\n[文档内容过长，已截断]"
            logger.warning("文档内容过长，已截断")
        
        # 执行补充
        return self.supplement_demand(
            original_request=original_request,
            doc_content=doc_content,
            user_feedback=additional_context
        )


def example_with_file():
    supplementer = DemandSupplementer()
    
    # 用户原始需求
    with open('test/test_data/req_ds1.txt', 'r', encoding='utf-8') as file:
        original_request = file.read()
    # 补充需求
    result = supplementer.supplement_from_files(
        original_request=original_request,
        file_paths=[
            "test/test_data/doc_ds1_md.md"
        ]
    )
    
    # 输出补充后的需求
    print("=" * 80)
    print("【补充后的完整需求】")
    print("=" * 80)
    
    demand = result.supplemented_demand
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
    for i, point in enumerate(result.key_points_added, 1):
        print(f"{i}. {point}")
    
    # 输出补充依据
    print("\n" + "=" * 80)
    print("【补充依据】")
    print("=" * 80)
    for i, evidence in enumerate(result.evidence, 1):
        print(f"{i}. {evidence}")
    
    # 输出置信度和待确认问题
    print(f"\n【置信度】: {result.confidence_score:.2%}")
    
    if result.questions_for_user:
        print("\n【需要确认的问题】")
        for i, question in enumerate(result.questions_for_user, 1):
            print(f"{i}. {question}")
    
    return result


# 示例2：直接传入文档内容
def example_with_content():
    supplementer = DemandSupplementer()

    with open('test_data/req_ds1.txt', 'r', encoding='utf-8') as file:
        original_request = file.read()
        print(original_request)

    with open('test_data/doc_ds1.txt', 'r', encoding='utf-8') as file:
        doc_content = file.read()
        print(doc_content)
    
    result = supplementer.supplement_demand(
        original_request=original_request,
        doc_content=doc_content
    )
    
    return result


# 执行示例
if __name__ == "__main__":
    # 运行示例
    result = example_with_file()
    
    # 保存结果到 JSON
    import json
    
    # 转换为字典并保存
    result_dict = result.model_dump()
    with open("test/test_results/supplemented_demand_md.json", "w+", encoding="utf-8") as f:
        json.dump(result_dict, f, ensure_ascii=False, indent=2)
    
    print("\n结果已保存到 supplemented_demand.json")
