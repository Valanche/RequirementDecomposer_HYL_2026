#coding:utf-8
import json
from typing import Optional


def print_decomp(file_path: str, row_id: Optional[str] = None):
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    if row_id is None:
        for item in data:
            print(item["row_number"])
            for idx, sub_req in enumerate(item["decomposed_list"]) :
                print(f"=== {idx+1} ===")
                desText = sub_req["description"].replace("\\n", "\n")
                print(desText)
    else:
        for item in data:
            if int(item["row_number"]) == int(row_id):
                for idx, sub_req in enumerate(item["decomposed_list"]) :
                    print(f"=== {idx+1} ===")
                    desText = sub_req["description"].replace("\\n", "\n")
                    print(desText)
                break


if __name__ == '__main__':
    print_decomp("ar_23/decomposed_output_5.json", "65") 
    