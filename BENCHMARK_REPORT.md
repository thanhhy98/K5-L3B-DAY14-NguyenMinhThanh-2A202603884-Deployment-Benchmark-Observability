# Benchmark & Observability Report — Day 14

> Copy file này thành `BENCHMARK_REPORT.md` trong repo của bạn và điền đầy đủ.
> Mọi con số phải lấy từ report JSON / CSV / screenshot thật, không ước lượng.

**Họ tên:** Nguyễn Minh Thành
**Ngày chạy:** 26/11/2026
**Môi trường:** Linux 7.0.0-44-generic x86_64; Docker 29.9.3; 4 CPUs; 1.71 GiB RAM

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | < 500 ms | Giới hạn độ trễ ở phần đuôi của phần lớn request; p95 ít bị che khuất bởi average khi có request chậm bất thường. |
| Error rate `/ask` | < 2 % | Giữ ít nhất 98% request thành công, đồng thời cho phép một lượng nhỏ lỗi upstream mô phỏng trong bài load test. |
| Accuracy trên golden dataset | ≥ 80 % | Dùng làm quality gate tối thiểu theo kết quả eval; CI đặt ngưỡng 85% nghiêm ngặt hơn trước khi merge. |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4.15 | 192.7 | 227.4 | 1705.0 | 3.00% | FAIL (error rate) |
| 10 | 33.21 | 200.4 | 286.4 | 1719.6 | 1.67% | PASS |
| 50 | 50.66 | 326.0 | 2459.9 | 3680.6 | 1.00% | FAIL (p95) |
| 100 | 40.88 | 1109.4 | 5282.4 | 5564.9 | 0.67% | FAIL (p95) |

**Nhận xét:** RPS không tăng tuyến tính: throughput tăng từ 4.15 RPS ở concurrency 1 lên 50.66 ở 50, rồi giảm xuống 40.88 ở 100. Ở concurrency cao, latency tăng mạnh (p95 lên 5,282.4 ms ở 100) trong khi error rate vẫn dưới ngưỡng 2%. Đây cho thấy thêm đồng thời không đảm bảo throughput tiếp tục tăng; tài nguyên và thời gian xử lý của agent tạo giới hạn. SLO tổng thể chỉ PASS ở concurrency 10.

**Kết luận:** Trong các mức đã đo, concurrency 10 là điểm duy nhất đạt cả hai SLO. Ở concurrency 50 và 100, p95 vượt xa ngưỡng 500 ms dù error rate thấp; vì vậy không nên chọn cấu hình chỉ theo throughput mà cần giữ p95 và tỷ lệ lỗi làm tiêu chí quyết định.

### 2.2 Tail latency

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 196.2 | 233.1 | 249.2 |
| 0.03 (mặc định) | 242.4 | 312.4 | 1681.6 |
| 0.1 | 351.6 | 1702.1 | 1726.8 |

**Nhận xét:** p95 và p99 nhạy với các request chậm ở phần đuôi phân phối: khi tăng `MOCK_SLOW_RATE` từ 0 lên 0.1, p95 tăng từ 233.1 ms lên 1,702.1 ms, trong khi average chỉ tăng từ 196.2 ms lên 351.6 ms. Average che khuất trải nghiệm của nhóm request chậm, nên SLO latency nên dùng percentile như p95/p99 thay vì average.

**Kết luận:** Khi `MOCK_SLOW_RATE` tăng từ 0.03 lên 0.1, p95 tăng từ 312.4 ms lên 1,702.1 ms (khoảng 5.5 lần), còn average chỉ tăng khoảng 45%. Tỷ lệ request chậm có thể khiến phần đuôi vượt SLO trước khi average phản ánh mức độ ảnh hưởng tương xứng.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.3% (1/23) | 91.3% (21/23) | 100% (23/23) |
| Avg tokens / câu | 56.6 | 109.0 | 117.8 |
| Tổng cost (USD) | 0.000397 | 0.000760 | 0.000826 |
| Cost / câu đúng (USD) | 0.00039675 | 0.00003619 | 0.00003593 |
| Quality gate | FAIL | PASS | PASS |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| security-02 | `token`, `hết hạn`, `chữ ký` | Thêm KB giải thích JWT và API key, bao gồm chữ ký và hạn dùng của token |
| scaling-03 | `cpu`, `memory`, `custom metrics` | Thêm KB giải thích HPA scale pod theo CPU, memory và custom metrics |

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:** v2 tăng accuracy từ 4.3% lên 91.3%; dù chi phí tổng cao hơn, chi phí trên câu đúng giảm từ $0.00039675 xuống $0.00003619. Sau khi bổ sung KB, v2 đạt 100% accuracy và cost trên câu đúng là $0.00003593. P95 của lần eval v2 ban đầu là 1,691.0 ms, còn lần eval sau sửa là 207.2 ms; lần kiểm tra cuối chạy với `MOCK_SLOW_RATE=0` và `MOCK_ERROR_RATE=0` để đo chất lượng ổn định, nên khác cấu hình với lần chạy trước.

**CI quality gate:** Trong GitHub Actions chạy khi có pull request, cài dependencies, khởi động agent v2 với `MOCK_ERROR_RATE=0`, rồi chạy eval với `--min-accuracy 0.85`. `run_eval.py` trả exit code `1` nếu accuracy thấp hơn ngưỡng hoặc có regression; khi đó job thất bại. Đặt job này làm required status check trong branch protection để chặn merge cho đến khi eval pass.

```yaml
- name: Run agent + eval
  working-directory: 06-lab-complete/benchmark-observability/develop
  run: |
    pip install -r requirements.txt
    AGENT_VERSION=v2 MOCK_ERROR_RATE=0 python app.py &
    sleep 3
    python eval/run_eval.py --url http://localhost:8000 --min-accuracy 0.85
```

---

## 4. Observability stack (production)

### 4.1 Screenshot

- [x] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals) — `screenshots/grafana-dashboard.png`
- [x] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian) — `screenshots/jaeger-slow-trace.png`
- [x] Một trace lỗi trong Jaeger (có event `exception`) — `screenshots/jaeger-error-trace.png`
- [x] Trang Alerts của Prometheus với ít nhất 1 alert đang **firing** — `screenshots/prometheus-alert-firing.png`

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` | 66.3 s | Error rate |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` | 126.6 s | Latency p95 |
| C | `LLM_MODEL=mock-llm-large` | `LLMCostBurnRateHigh` ($42.22/giờ) | 128.4 s | LLM cost burn rate |
| D | `docker pause` 2 instances | `AgentInstanceDown` (2 instances) | 40.2 s | `Instances up` và Prometheus Alerts |
| E | `AGENT_VERSION=v1` | Không có alert trong 60 s | Không firing trong 60 s | Không có panel hạ tầng phát hiện regression chất lượng |

Thí nghiệm A xác nhận lỗi upstream tăng cao sẽ kích hoạt `AgentHighErrorRate`; B xác nhận slow request làm p95 vượt ngưỡng và kích hoạt `AgentHighLatencyP95`; C cho thấy model lớn làm cost burn rate vượt ngưỡng. Thí nghiệm D pause hai agent trong 40.2 giây để xác nhận hai alert `AgentInstanceDown` cùng firing; sau khi chụp ảnh đã unpause và xác nhận các agent healthy. Thí nghiệm E không kích hoạt alert hạ tầng trong 60 giây—cần quality gate để phát hiện regression chất lượng.

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?** Theo dõi chất lượng đầu ra bằng golden-set evaluation, canary/version comparisons và feedback của người dùng; metrics hạ tầng như availability và latency không phát hiện câu trả lời sai nếu request vẫn thành công.

### 4.3 Debug bằng trace

Chọn 1 trace chậm nhất bạn tìm được:

- `trace_id`: `15862c1184f313b21276bbe3d38c4f16`
- Tổng thời gian: 1,700 ms (Jaeger)
- Span chiếm nhiều thời gian nhất: `chat mock-llm-small` (1,696.8 ms, khoảng 98.6% thời gian HTTP 1,720.7 ms)
- Dòng log tương ứng (grep theo `trace_id`):

```json
{"ts":"2026-11-26T13:09:09.964187+00:00","level":"INFO","service":"observable-agent","instance":"9fd4d13d5c4b","event":"llm_call","trace_id":"15862c1184f313b21276bbe3d38c4f16","span_id":"5eb22efa2b07745e","request_id":"c9d1abbab81c","model":"mock-llm-small","agent_version":"v2","input_tokens":95,"output_tokens":55,"cost_usd":4.7e-05,"llm_ms":1696.8}
```

Trace lỗi: `5532761b3053ab9f32b491ebaef0c9a2`, tổng thời gian 131 ms, kết quả HTTP 503. Dòng log liên quan:

```json
{"ts":"2026-11-26T13:09:08.953733+00:00","level":"INFO","service":"observable-agent","instance":"9fd4d13d5c4b","event":"llm_error","trace_id":"5532761b3053ab9f32b491ebaef0c9a2","span_id":"1ed559838869369c","request_id":"b403785e15f6","error":"Upstream LLM error: 503 Service Unavailable (mock)"}
{"ts":"2026-11-26T13:09:08.954378+00:00","level":"INFO","service":"observable-agent","instance":"9fd4d13d5c4b","event":"http_request","trace_id":"5532761b3053ab9f32b491ebaef0c9a2","span_id":"1ed559838869369c","request_id":"b403785e15f6","method":"POST","route":"/ask","status":503,"ms":129.3}
```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 44.05 | 470 | 2,300 | 3,900 | 59/5,159 (1.14%) |
| 3 | 48.82 | 230 | 2,100 | 4,800 | 61/5,793 (1.05%) |

**Giải thích kết quả:** Từ 1 lên 3 instance, throughput tăng từ 44.05 lên 48.82 RPS và p95 giảm 200 ms (khoảng 8.7%). Tuy nhiên p99 tăng từ 3,900 lên 4,800 ms, nên scale-out cải thiện phần lớn request nhưng không loại bỏ tail latency. Mẫu này phù hợp với độ trễ biến thiên của mock LLM (`MOCK_SLOW_RATE=0.03`) còn chi phối request chậm nhất; thêm instance không làm mỗi lệnh LLM nhanh hơn.

**Kết luận:** Scale từ 1 lên 3 instance tăng throughput khoảng 10.8%, giảm p50 240 ms và giảm p95 200 ms, nhưng p99 tăng 900 ms. Tỷ lệ lỗi `/ask` gần như không đổi (1.14% so với 1.05%). Cả hai lần chạy đều dưới SLO error rate 2%, nhưng p95 2,300 ms và 2,100 ms đều vượt SLO latency 500 ms. Vì vậy scale-out cải thiện latency điển hình nhưng chưa giải quyết được tail latency.

---

## 6. Kết luận

- 3 điều tôi học được về benchmark & observability:
  1. Throughput không tăng tuyến tính theo số instance: scale từ 1 lên 3 chỉ tăng từ 44.05 lên 48.82 RPS trong lần đo này.
  2. p95 giảm nhẹ khi scale-out nhưng p99 vẫn tăng; cần theo dõi tail latency thay vì chỉ nhìn average hoặc p50.
  3. Trace ID liên kết được trace Jaeger với JSON logs, giúp xác định LLM call chiếm phần lớn thời gian và phân biệt lỗi upstream 503.
- Nếu đưa agent này lên production thật, bạn sẽ thêm metric / alert nào nữa?

  Theo dõi độ sâu hàng đợi và thời gian chờ, timeout/retry theo upstream, token và chi phí theo model/tenant, cùng accuracy trên golden set theo phiên bản. Đặt cảnh báo cho backlog tăng kéo dài, timeout upstream và quality-gate regression.
