# -*- coding: utf-8 -*-
import os
from typing import List
from langchain_community.document_loaders import PyPDFLoader


class DocumentLoader:
    def __init__(self, custom_loader_map:map = None):
        default_loader_map = {
            '.pdf': PyPDFLoader,
            '.txt': None,
            '.md': None,
            '.MD': None,
            '.mdx': None,
            '.markdown': None
        }
        self.loader_map = default_loader_map
        if custom_loader_map is not None:
            self.loader_map = custom_loader_map

    def load_document(self, file_path: str) -> str:
        """加载文档内容"""
        ext = os.path.splitext(file_path)[1].lower()
        
        # 特殊处理文本文件(如果没有配置对应loader)
        if ext in ['.md', '.MD', '.mdx', '.markdown', '.txt']:
            if self.loader_map[ext] is None:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return f.read()
                
        if ext not in self.loader_map:
            raise ValueError(f"不支持的文件格式: {ext}")
        
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
