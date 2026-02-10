#coding:utf-8
import json
from evaluate import load
import jieba

def tokenize_chinese(text: str) -> str:
    """
    使用 Jieba 分词对中文文本进行分词。
    """
    return ' '.join(jieba.cut(text))

def load_descriptions(file_path):
    """从JSON文件中加载描述，并按行号映射。"""
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return {item['row']: item['concatenated'] for item in data if item.get('concatenated')}

if __name__ == '__main__':
    # 0. 加载所有评估器
    print("正在加载评估指标 (BERTScore, ROUGE, BLEU, METEOR)...")
    bertscore = load("bertscore")
    rouge = load('rouge')
    bleu = load('bleu')
    meteor = load('meteor')
    print("评估指标加载完毕。")
    
    # 1. 加载数据
    print("\n正在加载预测和参考数据...")
    predictions_map = load_descriptions('ar_23/ar_descriptions_1.json')
    references_map = load_descriptions('ar_23/ar_descriptions_ref.json')
    print("数据加载完毕。")
    
    # 2. 对齐数据
    predictions_raw = []
    references_raw = []
    rows = []
    
    for row, pred_text in predictions_map.items():
        if row in references_map:
            predictions_raw.append(pred_text)
            references_raw.append(references_map[row])
            rows.append(row)
            
    if not predictions_raw:
        print("\n未能从文件中加载或对齐任何有效的预测/参考对。脚本终止。")
    else:
        print(f"\n成功对齐 {len(predictions_raw)} 个数据对。开始计算指标...")

        # 3. 计算所有指标
        try:
            # --- 3a. 计算 BERTScore (一次性完成) ---
            print("  - 计算 BERTScore...")
            bert_results = bertscore.compute(predictions=predictions_raw, references=references_raw, lang="zh")
            print("BERTScore 计算完成。")

            # 4. 整理并保存结果
            
            combined_per_row_scores = []
            total_bert_precision = 0
            total_bert_recall = 0
            total_bert_f1 = 0
            total_rouge1 = 0
            total_bleu = 0
            total_meteor = 0
            
            print("\n正在逐行计算 ROUGE, BLEU, METEOR 并整合所有分数...")
            for i, row in enumerate(rows):
                # 获取该行的 BERTScore
                bert_p = bert_results['precision'][i]
                bert_r = bert_results['recall'][i]
                bert_f1 = bert_results['f1'][i]

                # 为其他指标单独准备该行的数据
                pred_raw_single = predictions_raw[i]
                ref_raw_single = references_raw[i]
                pred_tok_single = tokenize_chinese(pred_raw_single)
                ref_tok_single = tokenize_chinese(ref_raw_single)

                # 单独计算 ROUGE, BLEU, METEOR
                rouge1_score = rouge.compute(predictions=[pred_tok_single], references=[ref_tok_single])['rouge1']
                bleu_score = bleu.compute(predictions=[pred_tok_single], references=[ref_tok_single])['bleu']
                meteor_score_val = meteor.compute(predictions=[pred_tok_single], references=[ref_tok_single])['meteor']
                
                # 合并所有单行结果
                combined_per_row_scores.append({
                    "row": row,
                    "bert_precision": bert_p,
                    "bert_recall": bert_r,
                    "bert_f1": bert_f1,
                    "rouge-1": rouge1_score,
                    "bleu": bleu_score,
                    "meteor": meteor_score_val
                })
                
                # 累加总分用于计算平均分
                total_bert_precision += bert_p
                total_bert_recall += bert_r
                total_bert_f1 += bert_f1
                total_rouge1 += rouge1_score
                total_bleu += bleu_score
                total_meteor += meteor_score_val
                print(f"  - 已处理 Row {row}")
            
            # 计算平均分
            num_items = len(rows)
            combined_average_scores = {
                "bert_precision": total_bert_precision / num_items,
                "bert_recall": total_bert_recall / num_items,
                "bert_f1": total_bert_f1 / num_items,
                "rouge-1": total_rouge1 / num_items,
                "bleu": total_bleu / num_items,
                "meteor": total_meteor / num_items
            }
            
            output_data = {
                "per_row_scores": combined_per_row_scores,
                "average_scores": combined_average_scores
            }

            output_file_path = 'ar_23/all_scores_1.json'
            with open(output_file_path, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, ensure_ascii=False, indent=2)
            
            print(f"\n所有指标结果已保存到 '{output_file_path}'")
            
            print("\n--- 平均分数 ---")
            print(f"平均 BERT Precision: {combined_average_scores['bert_precision']:.4f}")
            print(f"平均 BERT Recall:    {combined_average_scores['bert_recall']:.4f}")
            print(f"平均 BERT F1:        {combined_average_scores['bert_f1']:.4f}")
            print(f"平均 ROUGE-1:        {combined_average_scores['rouge-1']:.4f}")
            print(f"平均 BLEU:           {combined_average_scores['bleu']:.4f}")
            print(f"平均 METEOR:         {combined_average_scores['meteor']:.4f}")

        except Exception as e:
            print(f"\n计算指标时发生错误: {e}")
            import traceback
            traceback.print_exc()
            print("请确保已安装所需库: pip install evaluate bert-score torch transformers jieba")