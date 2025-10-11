# Tiêu chí đánh giá (dùng cho human evaluation)

Mục tiêu: so sánh 2 phiên bản generator — Chain-of-Thought (CoT) vs Minimal prompt — trên cùng một tập dữ liệu (ví dụ: JFLEG). Mỗi bản sẽ được đánh giá bởi rater con người theo các tiêu chí chuẩn dưới đây.

Hướng dẫn chung:
- Mỗi rater đọc `source_text` (JFLEG post) và hai cột `cot_output` và `minimal_output` (được hiển thị cạnh nhau, thứ tự ngẫu nhiên để tránh bias). Rater cho điểm từng bản theo các tiêu chí dưới.
- Điểm sử dụng thang 1-5 (1 = rất kém, 5 = xuất sắc) trừ khi có ghi khác.
- Nếu rater không thể quyết định (ambiguous), dùng cột `comments` để ghi lý do.

Tiêu chí (mỗi tiêu chí có thể đánh điểm 1-5):

1) Tính chính xác nội dung (Content Accuracy)
- Mô tả: Sản phẩm có đúng/đủ ý so với `source_text`? (không thêm hiểu biết sai lệch, không bỏ ý quan trọng)
- 5 = hoàn toàn chính xác và đầy đủ; 1 = sai hoặc thêm thông tin sai.

2) Độ tự nhiên / Fluency
- Mô tả: Câu hỏi/đáp án có mượt, tự nhiên, không lỗi chính tả/ngữ pháp?
- 5 = rất tự nhiên; 1 = khó đọc, nhiều lỗi.

3) Tính phù hợp mục tiêu giáo dục (Pedagogical appropriateness)
- Mô tả: Mức độ phù hợp với mục tiêu học tập (ví dụ: kiểm tra ngữ pháp A2 vs C1), độ khó có phù hợp không?
- 5 = hoàn toàn phù hợp; 1 = không phù hợp (quá khó/dễ hoặc không sát chủ đề).

4) Chất lượng lựa chọn (MCQ distractor quality) — chỉ cho MCQ
- Mô tả: Distractors có hợp lý, không quá dễ loại bỏ, không đánh lừa vô nghĩa?
- 5 = distractors rất tốt; 1 = distractors tệ (sai lô-gic, trùng lặp, quá dễ).

5) Sự khác biệt thông tin / Hallucination (Hallucination)
- Mô tả: Bản có thêm thông tin sai lệch không (ví dụ: bịa đặt chi tiết, đưa thông tin không có trong `source_text`)?
- 5 = không có hallucination; 1 = chứa hallucination nặng.

6) Tổng điểm / Preferential choice
- Mô tả: Rater chọn 1 trong {"Prefer CoT", "Prefer Minimal", "No Preference"} nếu họ phải chọn phiên bản tốt hơn tổng thể.

Ghi chú về đánh giá:
- Để đánh giá công bằng, hãy random hóa cột `cot_output`/`minimal_output` vị trí trong CSV trước khi phân phát cho rater.
- Nếu đánh giá nhiều rater, lưu `rater_id` và tính IAA (Cohen's Kappa) cho từng tiêu chí.
- Tích lũy `comments` để rút kinh nghiệm prompt engineering.

---

Mẫu bảng CSV/Excel (header):
id,source_text,cot_output,minimal_output,accuracy_cot,fluency_cot,pedagogy_cot,distractor_cot,hallucination_cot,accuracy_min,fluency_min,pedagogy_min,distractor_min,hallucination_min,prefer,comments,rater_id
