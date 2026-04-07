from pydantic import BaseModel, Field
from typing import List, Optional
import json

# 定义需求本体的结构
class DemandBody(BaseModel):
    """需求本体结构"""
    demand_value: str = Field(description="需求价值：该需求旨在解决何种核心问题，或为用户及业务带来何种收益")
    demand_scenario: str = Field(description="需求场景：该需求的适用业务场景与具体触发条件")
    demand_description: str = Field(description="需求描述：该需求需实现功能的详细说明，包括主要流程与关键交互")
    target_users: str = Field(description="目标用户：该需求的明确使用人群，例如某类终端用户或系统角色")
    constraints: str = Field(description="限制约束：实现该需求需满足的约束条件，如用户前置操作、技术或业务限制等")
    external_dependencies: str = Field(description="外部依赖：该需求所依赖的外部系统、组件或服务")
    performance_metrics: str = Field(description="性能指标：该需求的性能要求，例如响应时间、并发能力等指标，需明确对比基线或提升目标")
    rom_ram: str = Field(description="ROM&RAM：该需求对设备存储（ROM）与内存（RAM）的占用要求，需明确对比基线或优化目标")
    acceptance_criteria: str = Field(description="验收标准：该需求通过验收的判定条件与依据，例如功能完整性、性能达成度等维度")
    acceptance_devices: str = Field(description="验收设备：验收该需求所需的设备类型与测试环境，如特定型号手机、操作系统版本等")
    product_difference_analysis: str = Field(description="使用产品差异分析：该需求在不同设备或平台上的使用行为差异；如无差异，需明确说明")
    ecosystem_impact: str = Field(description="2D生态：该需求对面向开发者的软件生态建设可能产生的影响")

class SupplementResult(BaseModel):
    """需求补充的完整输出结果"""
    supplemented_demand: DemandBody = Field(description="补充后的完整需求本体")
    key_points_added: List[str] = Field(description="补充的关键要点列表，说明在原始需求基础上补充了哪些内容")
    evidence: List[str] = Field(description="补充依据列表，说明每个补充点所依据的文档来源或推理逻辑")
    confidence_score: float = Field(description="置信度评分（0-1），表示补充内容的可信程度")
    questions_for_user: List[str] = Field(description="需要用户确认的问题，特别是文档中存在矛盾或歧义的地方")