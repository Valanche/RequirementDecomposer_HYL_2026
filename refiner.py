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
from langchain_community.document_loaders import PyPDFLoader, TextLoader, UnstructuredMarkdownLoader


load_dotenv()
logger = logging.getLogger("refiner")

# --- LangChain Model and Prompt Definition ---

llm = ChatOpenAI(
    model=os.getenv("OPENAI_MODEL_NAME_REFINE", "gpt-4-turbo"),
    api_key=os.getenv("OPENAI_API_KEY_REFINE") or os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL_REFINE") or os.getenv("OPENAI_BASE_URL"),
    temperature=0
)

schema_file_path = "../models/supplement_req.json"
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
    
    def __init__(self, model_name: str = "gpt-4", temperature: float = 0):
        self.llm = llm
        
        self.structured_llm = self.llm.with_structured_output(SupplementResult)

        # 文档加载器映射
        self.loader_map = {
            '.pdf': PyPDFLoader,
            '.txt': None,
            '.md': None,
            '.MD': None,
            '.mdx': None,
            '.markdown': None
        }

    def load_document(self, file_path: str) -> str:
        """加载文档内容"""
        ext = os.path.splitext(file_path)[1].lower()
        
        if ext not in self.loader_map:
            raise ValueError(f"不支持的文件格式: {ext}")
        
        # 特殊处理文本文件
        if ext in ['.md', '.MD', '.mdx', '.markdown', '.txt']:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
            
        loader_cls = self.loader_map[ext]
        
        # 处理 PDF 和 Markdown
        loader = loader_cls(file_path)
        documents = loader.load()
        
        # 合并所有页面/文档内容
        return "\n".join([doc.page_content for doc in documents])
    
    def load_multiple_documents(self, file_paths: List[str]) -> str:
        """加载多个文档并合并"""
        contents = []
        for file_path in file_paths:
            try:
                content = self.load_document(file_path)
                contents.append(f"=== 文档: {os.path.basename(file_path)} ===\n{content}")
            except Exception as e:
                print(f"加载文档 {file_path} 失败: {e}")
        
        return "\n\n".join(contents)
    
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
            additional_context: 额外的上下文信息
        
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
        doc_content = self.load_multiple_documents(file_paths)
        
        # 限制文档长度（避免超 token）
        max_chars = 10000
        if len(doc_content) > max_chars:
            doc_content = doc_content[:max_chars] + "\n\n[文档内容过长，已截断]"
        
        # 执行补充
        return self.supplement_demand(
            original_request=original_request,
            doc_content=doc_content,
            user_feedback=additional_context
        )
