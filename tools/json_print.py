#coding:utf-8
import json
from typing import Optional


def print_decomp(file_path: str, row_id: Optional[str] = None):
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    if row_id is None:
        for item in data:
            print(item["row_number"])
            for sub_req in item["decomposed_list"]:
                print(sub_req["description"])
    else:
        for item in data:
            if int(item["row_number"]) == int(row_id):
                for sub_req in item["decomposed_list"]:
                    print(sub_req["description"])
                break


if __name__ == '__main__':
    print_decomp("ar_23/decomposed_output.json", "65") 
    