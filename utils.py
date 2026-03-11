import json
import logging
from typing import Dict, List, Optional


logger_file = logging.getLogger("utils.file")

def load_from_json(file_path: str) -> Optional[List[Dict]]:
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if data is None:
                logger_file.warning(f"{file_path}内容为空")
            return data
    except FileNotFoundError:
        logger_file.exception(f"{file_path}不存在")
        return None
    except json.JSONDecodeError as e:
        logger_file.exception(f"解析{file_path}时发生未知错误:")
        return None
    except Exception as e:
        logger_file.exception(f"读取{file_path}时发生未知错误:")
        return None

def load_active_rules_from_json(file_path: str) -> Optional[List[str]]:
    """
    从json文件中加载生效的规则（分解/评估），将其作为字符串列表返回。

    Args:
        file_path (str): 包含规则的文本文件路径。

    Returns:
        Optional[List[str]]: 规则字符串列表，如果文件不存在或为空则返回None。
    """
    try:
        data = load_from_json(file_path)
        if "active_rules" not in data:
            logger_file.error(f"{file_path}格式错误")
            return None
        return data["active_rules"]
    except FileNotFoundError:
        print(f"[ERROR] 规则文件未找到: {file_path}")
        return None
    except Exception as e:
        print(f"[ERROR] 读取规则文件时发生未知错误: {e}")
        return None


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
                    
                logger_file.info(f"读取了{file_path}中{len(data)}条需求，预期为前{limit}条")
                return data
            else:
                logger_file.error(f"{file_path}内容格式错误")
                return None
    except FileNotFoundError:
        logger_file.exception(f"{file_path}不存在")
        return None
    except json.JSONDecodeError as e:
        logger_file.exception(f"解析{file_path}时发生未知错误:")
        return None
    except Exception as e:
        logger_file.exception(f"读取{file_path}时发生未知错误:")
        return None

def save_results_to_json(results: List[Dict], output_path: str):
    
    """
    将需求列表保存为格式化的JSON文件。

    Args:
        results (List[Dict]): 包含所有行分解结果的列表。
        output_path (str): 输出的JSON文件路径。
    """
    try:
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
            
        logger_file.info(f"结果已成功保存至{output_path}。")

    except Exception as e:
        logger_file.exception(f"保存{output_path}时发生未知错误:")