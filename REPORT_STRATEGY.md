# Lab 17 - Multi-Memory Agent Strategy Report

## Tổng quan chiến thuật

Lab xây dựng agent với 4 memory layer, mỗi layer phục vụ một mục đích khác nhau trong việc lưu trữ và truy xuất thông tin.

---

## 1. Short-term Memory (E01, E10) - Đã có sẵn

### Cơ chế
- **Buffer**: Lưu tất cả messages, token tăng tuyến tính
- **Summary**: Nén old turns thành summary
- **Sliding Window**: `system/state summary + last K turns` - **default của lab**

### Chiến thuật Compaction
Compaction không phải "tóm tắt văn hóa" mà phải ưu tiên:
1. **State**: Trạng thái hiện tại của task/project
2. **Decisions**: Các quyết định đã đưa ra
3. **TODO/Constraints**: Việc cần làm và các ràng buộc

### Ví dụ E10
Query: "Deadline review là mấy giờ?"
- Durable note giữ `REVIEW-DEADLINE-1600`, `Friday`, `16:00` ngay cả khi raw turn đã bị evict
- Sliding window với `max_recent_messages=4` vẫn giữ được deadline vì có trong durable note

---

## 2. Long-term Memory (E02, E03, E08, E09) - TODO 1/4

### Chiến thuật: Context Block + Edges Fact Search

```python
def retrieve_long_term(self, user_id, thread_id, query):
    # 1) Prime eval thread - đặt query vào context để Zep đánh giá relevance
    prime_eval_thread(self.client, user_id, thread_id, query)

    # 2) Lấy Context Block - tóm tắt user graph theo relevance
    user_context = self.client.thread.get_user_context(thread_id=thread_id)
    context_block = user_context.context

    # 3) Append edges - lấy facts với validity ranges cho recency/conflict
    facts = graph.search(user_id, query, scope="edges", limit=20)
    return join_nonempty([context_block, fact_text])
```

### Tại sao dùng Context Block?
- **User-scoped**: Tự động isolate memory giữa các users (E09)
- **Relevance-ranked**: Zep đánh giá và trả về facts relevant với query
- **Cross-session**: Nhớ preferences, TODOs từ session trước (E02, E03)

### Recency/Conflict (E08)
Query: "Project BLUEBIRD-42 dùng tech stack gì?"
- Sau khi session cập nhật từ Python → TypeScript + NestJS
- Edges fact search với `limit=20` đảm bảo lấy cả fact cũ và mới
- Fact mới có `valid_at` gần hơn → được ưu tiên

### User Isolation (E09)
Query của `lan-lab17` chỉ thấy:
- `LOTUS-88`, `Java`, `Spring Boot` ✓
- **KHÔNG** thấy `ORCHID-27` của `minh-lab17` ✗

---

## 3. Episodic Memory (E04, E05) - TODO 2/4

### Chiến thuật: User Graph Episode Search

```python
def retrieve_episodic(self, user_id, query):
    results = client.graph.search(
        user_id=user_id,          # KHÔNG phải graph_id!
        query=cap_query(query),   # Truncate >400 chars
        scope="episodes",         # Lấy session trajectories
        limit=15,
    )
    return render_graph_search(results, episode_char_cap=180)
```

### Tại sao dùng `episode_char_cap=180`?
- Session episodes có thể rất verbose
- Marker-bearing reflections (như `ASYNC-FIX-20`) có thể bị đẩy ra ngoài budget
- Cap 180 chars giữ được nhiều distinct episodes hơn

### Ví dụ E04
Query: "Lần trước fix async HTTP timeout bằng cách nào?"

Trajectory cần recall:
```
tried: increase timeout → failed
worked: reuse aiohttp ClientSession + concurrency=20
reflection: connection churn, không phải timeout threshold, mới là vấn đề
```

Markers bắt buộc: `ClientSession`, `concurrency=20`, `ASYNC-FIX-20`

---

## 4. Semantic Memory (E06, E11) - TODO 3/4

### Chiến thuật: Standalone Graph Search

```python
def retrieve_semantic(self, graph_id, query):
    q = cap_query(query)
    try:
        results = client.graph.search(
            graph_id=graph_id,      # KHÔNG dùng user_id!
            query=q,
            scope="episodes",        # Giữ literal markers
            limit=8,
        )
    except Exception:
        # Fallback to nodes
        results = client.graph.search(
            graph_id=graph_id,
            query=q,
            scope="nodes",
            limit=8,
        )
    return render_graph_search(results)
```

### Tại sao dùng `graph_id` thay vì `user_id`?
- Semantic memory = domain knowledge **dùng chung**, không thuộc user nào
- `data/knowledge.jsonl` chứa: payment rules, connection pooling, retry policies
- User preferences không nên lẫn vào semantic search (E06/E11)

### Tại sao dùng `scope="episodes"`?
- Giữ raw document text với literal markers: `PAYMENT-RULE-3`, `Idempotency-Key`
- `scope="auto"` trả extracted facts → **mất markers** → FAIL

### Ví dụ E06
Query: "Payment retry policy?"

Markers bắt buộc:
- `Idempotency-Key`
- `max-3-retries`
- `exponential-backoff`

---

## 5. Mixed Context Assembly (E07) - TODO 4/4

### Chiến thuật: Budget Manager với Priority

```python
def assemble_context(self, layers):
    return self.budget.assemble(layers)
    # Budget: 10/4/3/3 (short-term/long-term/episodic/semantic)
    # Priority: short_term > long_term > episodic > semantic
```

### Ví dụ E07
Query: "Viết script data pipeline bằng Python với payment retry"

Cần cả 2 layers:
- **Long-term**: Python preference (E02)
- **Semantic**: Idempotency-Key, retry policy (E06)

### Budget Allocation
| Layer | % | Tokens (8000 total) |
|-------|---|---------------------|
| short_term | 10% | 800 |
| long_term | 4% | 320 |
| episodic | 3% | 240 |
| semantic | 3% | 240 |

---

## 6. Phân tích Benchmark

### Layer nào có hit rate thấp nhất?
- **Episodic** (E04, E05): Thường khó nhất vì cần recall specific trajectory
- Lí do: Session verbose → marker-bearing reflections có thể bị cắt

### Case nào retrieve nhiều token nhất?
- **E08** (recency/conflict): Cần cả Context Block + edges search với limit=20
- **E07** (mixed): Cần kết hợp long-term + semantic

### E07 cần kết hợp memory nào?
1. **Long-term**: Python preference (fact từ user graph)
2. **Semantic**: Payment retry policy (từ standalone graph)
3. Evidence bắt buộc: cả `Python` và `Idempotency-Key`

### Token reduction vs no-memory baseline
- **No-memory**: Không có reduction vì context = trống → hit rate rất thấp
- **Memory-enabled**: Reduction cao nhưng hit rate cao vì lấy đúng evidence
- Trade-off: Budget trimming có thể miss edge cases nhưng đảm bảo context fit

---

## 7. Privacy & Security

### Right to be Forgotten
```bash
python -m src.forget --user-id minh-lab17
```

Xóa:
- Zep user + user-scoped memory
- Redis keys của user

**KHÔNG xóa**: Semantic/compiled KB (domain knowledge dùng chung)

### User Isolation
- Mỗi long-term/episodic call phải dùng đúng `user_id`
- Sai `user_id` = data-leak bug (E09)

---

## 8. Lessons Learned

### Điều quan trọng nhất
1. **Scope đúng cho từng layer**:
   - Long-term: Context Block
   - Episodic: `scope="episodes"` với `user_id`
   - Semantic: `scope="episodes"` với `graph_id` (KHÔNG dùng `scope="auto"`)

2. **cap_query()**: Zep reject queries >400 chars

3. **episode_char_cap=180**: Giữ nhiều distinct episodes trong episodic budget

4. **User isolation**: KHÔNG bao giờ dùng sai user_id

### Tại sao 4 layers?
- **Short-term**: Conversation hiện tại (gần, nhanh)
- **Long-term**: Facts/preferences xuyên session (ổn định)
- **Episodic**: Trajectories/outcomes (học từ quá khứ)
- **Semantic**: Domain knowledge chung (dùng lại được)
