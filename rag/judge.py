import json
from typing import List, Dict, Any, Optional
import vertexai
from vertexai.generative_models import GenerativeModel
from .logger import get_logger
from .utils import get_google_project_id

logger = get_logger()

class RagJudge:
    def __init__(self, project_id: Optional[str] = None, location: str = "us-central1"):
        # 自动推断 Project ID
        if not project_id:
            project_id = get_google_project_id()
            
        # 初始化 Vertex AI
        vertexai.init(project=project_id, location=location)
        self.model = GenerativeModel("gemini-2.5-flash")

    def audit_claims(self, text: str) -> List[Dict[str, Any]]:
        """
        根据 PR 15.4.1 定义的强断言类型进行语义审计
        """
        prompt = f"""
        你是一个严谨的学术论文审计员。请识别以下文本中的“强断言（Strong Claims）”。
        强断言包括：因果关系、比较、定量数据、普遍化陈述、政策建议、最高级描述。
        
        请以 JSON 数组格式返回，每个对象包含：
        - claim_text: 句子原文
        - claim_type: 断言类型（因果/比较/定量/普遍化/建议/最高级）
        - reason: 为什么需要证据支撑
        
        待审计文本：
        {text}
        """
        
        try:
            response = self.model.generate_content(prompt)
            # 清理 Markdown 代码块包裹
            raw_text = response.text.strip().replace("```json", "").replace("```", "")
            return json.loads(raw_text)
        except Exception as e:
            logger.error(f"解析 Audit 结果失败: {e}")
            return []

    def verify_support(self, sentence: str, evidence_texts: List[str]) -> Dict[str, Any]:
        """
        执行 PR 15.4.3 的语义支撑度校验
        返回 support_score (0.0 - 1.0) 和 status
        """
        context = "\n---\n".join(evidence_texts)
        prompt = f"""
        你是一个学术事实核查员。
        请对比“学生断言”与“原文证据”，判定证据是否能够支撑断言。
        
        学生断言：{sentence}
        
        原文证据：
        {context}
        
        请严格按以下 JSON 格式返回：
        {{
            "support_score": 0.0到1.0之间的浮点数,
            "status": "OK" 或 "WEAK" 或 "MISSING",
            "critique": "简短的评价，说明为什么支撑或不支撑"
        }}
        """
        
        try:
            response = self.model.generate_content(prompt)
            raw_text = response.text.strip().replace("```json", "").replace("```", "")
            return json.loads(raw_text)
        except Exception as e:
            logger.error(f"解析 Verify 结果失败: {e}")
            return {"support_score": 0.0, "status": "MISSING", "critique": f"API 解析失败: {e}"}

    def expand_query(self, text: str) -> List[str]:
        """
        Query Expansion: 生成 3 个学术搜索变体
        """
        prompt = f"""
        你是一个学术搜索引擎的查询优化器。
        请将用户的输入问题改写为 3 个不同的学术搜索查询词（Query Variants），以便在向量数据库中获得更好的召回率。
        
        用户输入："{text}"
        
        要求：
        1. 变体应涵盖同义词、更专业的学术术语或相关概念。
        2. 必须且仅返回一个纯 JSON 字符串列表。
        3. 严禁包含 Markdown 格式（如 ```json），严禁包含任何解释性文字。
        
        示例输出：
        ["variant 1", "variant 2", "variant 3"]
        
        你的输出：
        """
        try:
            response = self.model.generate_content(prompt)
            raw = response.text.strip().replace("```json", "").replace("```", "").strip()
            variants = json.loads(raw)
            if isinstance(variants, list):
                return [str(v) for v in variants[:3]] # 确保只取前3个
            return []
        except Exception as e:
            logger.warning(f"Query expansion failed: {e}")
            return []