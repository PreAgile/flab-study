# 04-04. ZGC and Shenandoah — sub-ms STW의 두 GC

> 2018년 ZGC (Oracle), 2019년 Shenandoah (Red Hat) — 거의 동시에 등장한 **sub-millisecond STW** 의 두 GC. 둘 다 같은 목표를 다른 메커니즘으로.
> 핵심 발상: **mutator와 동시에 객체 이동까지** 수행하려면 mutator가 항상 정확한 주소를 보도록 해야 한다 — **Read Barrier**로 해결.
> 시니어가 알아야 할 것: latency-critical 시스템 (HFT, 실시간 게임, 큰 capacity web)이 채택. **Heap 크기 → ZGC, 운영 호환성 → Shenandoah**가 일반 가이드.

---

## 이 문서의 사용법

1. **0장 마인드맵을 먼저 외운다**.
2. **1~5장을 순서대로 학습한다**.
3. **6장 면접 워크플로우** + **7장 꼬리질문**.

---

## 0. 마인드맵 — 면접 종이에 그릴 그림

### 루트 한 문장 (anchor)

> **"ZGC와 Shenandoah는 Read Barrier로 객체 이동까지 mutator와 concurrent하게 진행한다. ZGC는 Colored Pointer + Multi-mapping, Shenandoah는 표준 mmap + 더 portable."**

### 5개 가지 — 순서를 외운다

```
              [ROOT: Concurrent Evacuation + Read Barrier]
                                  │
       ┌─────────┬──────────────────┼──────────────────┬─────────┐
       │         │                  │                  │         │
      ① Concurrent ② ZGC          ③ Shenandoah     ④ pmap     ⑤ 선택
   Evacuation의   Colored Pointer  Brooks→LRB       함정       기준
   필요성         + Multi-mapping  (옛→현재)
       │         │                  │                  │         │
   ┌───┼───┐  ┌──┼──┐           ┌───┼───┐         ┌────┼────┐
  STW의   Read  64-bit  3 view  Brooks  LRB        가상 3배  Heap 크기
  본질    Barrier ptr   가상      pointer 동등     vs RSS    OS/JDK
  GC 협력 (LRB) state   주소     header  ZGC      메트릭    Generational
```

### 가지별 핵심 키워드

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① Concurrent Evacuation** | STW의 본질 (정확성) | Read Barrier가 해결 | Mutator가 항상 최신 주소 |
| **② ZGC 메커니즘** | Colored Pointer (state bits) | Multi-mapping (3 view) | LRB (1 instruction check) |
| **③ Shenandoah 진화** | Brooks Pointer (옛, header 8B) | LRB (JDK 15+, 표준 헤더) | ZGC와 점차 수렴 |
| **④ pmap 함정** | 가상 3배, RSS 1배 | 모니터링 도구 학습 | cgroup memory.current |
| **⑤ 선택 기준** | Heap 크기 (32GB / 100GB) | JDK 버전 (21+ Gen ZGC) | 운영 portability |

### 면접 답변 흐름

> 면접관 질문 → 루트 문장 → 해당 가지 → 키워드 3개 → 인접 가지로 확장

---

## 1. 가지 ①: Concurrent Evacuation — 왜 Read Barrier가 필요한가

### 1.1 핵심 질문

> "객체를 mutator와 동시에 이동(evacuate)하는 게 왜 어려운가요? 어떻게 해결?"

### 1.2 키워드 1 — STW Evacuation의 본질

```
[기존 GC (G1까지) — STW로 evacuate]
1. 모든 mutator 정지 (STW)
2. 객체 A를 새 주소 B로 복사
3. 모든 ref를 A → B로 갱신
4. mutator 재개

→ 단순. 그러나 STW 길음 (객체 많으면 수십~수백 ms).
```

핵심: **정확성은 STW가 보장**. Mutator가 안 움직이니 안전.

### 1.3 키워드 2 — Concurrent Evacuation의 문제

```
[Concurrent Evacuation 시도]
1. mutator 정지 안 함
2. 객체 A를 새 주소 B로 복사 (concurrent)
3. mutator가 A의 ref를 들고 있음 → 어떻게 정확성?

문제:
   - Mutator가 옛 주소 A를 읽으면 옛 데이터 (또는 빈 메모리) 봄
   - Race condition
   - 메모리 손상
```

### 1.4 키워드 3 — Read Barrier가 해결

```
[Read Barrier 도입]
mutator가 ref를 읽을 때마다 GC 상태 확인:
   raw_ptr = obj.field;
   if (raw_ptr이 옛 주소) {
       raw_ptr = forward_to_new_addr(raw_ptr);  // GC 보조 함수
   }
   use raw_ptr;

→ mutator는 항상 최신 주소 받음
→ Concurrent Evacuation 안전
→ STW < 1ms (Mark 시작/끝의 짧은 sync만)
```

**비용**: 매 ref 읽기에 추가 instruction 2~5개 (~2~5% throughput).
**이점**: STW가 수십~수백 ms에서 < 1ms로.

---

## 2. 가지 ②: ZGC 메커니즘 — Colored Pointer + Multi-mapping

### 2.1 핵심 질문

> "ZGC의 Colored Pointer가 무엇이고 Multi-mapping과 어떻게 연결되나요?"

### 2.2 키워드 1 — Colored Pointer

```
일반 64-bit pointer: [64 bits: 실제 주소]
ZGC colored pointer:
   [unused][marked0:1][marked1:1][remapped:1][finalizable:1][addr:42]
                                                              ↑
                                                      실제 주소 영역

State 비트:
   - marked0: 이번 marking cycle에 mark됐는가?
   - marked1: 이전 marking cycle에 mark됐는가? (snapshot)
   - remapped: relocated된 후 ref가 갱신됐는가?
   - finalizable: finalize 대기 중인가?

→ Pointer 자체에 GC 상태 정보
→ 별도 mark bitmap 불필요
→ GC state check가 1 instruction (mask + cmp)
```

### 2.3 키워드 2 — Multi-mapping

```
한 물리 메모리 페이지(4KB)를 여러 가상 주소에 mapping:

   Physical page X ──┬──→ marked0_view + offset
                    ├──→ marked1_view + offset
                    └──→ remapped_view + offset

용도:
   colored pointer의 state 비트로 어느 view 통해 접근할지 결정.
   각 view는 OS의 분리된 가상 주소이지만 같은 데이터.

운영 함정:
   pmap이 가상 주소 합산 → 3배 보고 (큰 함정).
   RSS (cgroup memory.current)는 1배 — 정확.
```

→ 가지 ④에서 더.

### 2.4 키워드 3 — LRB (Load Reference Barrier)

```
Java 코드: x = obj.field;

JIT가 inline:
   raw = load(field);
   if ((raw & state_mask) != expected_state) {
       raw = lrb_slow_path(raw);  // GC 보조 호출
   }
   x = raw;

x86 어셈블리 (개념):
   mov  rax, [obj+offset]   ; raw load
   test rax, state_mask     ; state check
   jnz  slow_path           ; mismatch → slow path
   ; ... use rax

비용: ~2~5 cycles (fast path)
```

### 2.5 ZGC의 Concurrent Cycle

```
1. Mark Phase (concurrent + 짧은 STW)
   - Pause Mark Start (STW, ~0.1ms): GC Roots scan
   - Concurrent Mark: mutator와 동시 reachable 객체 mark
   - Pause Mark End (STW, ~0.1ms): 변경분 finalize

2. Select Collection Set
   - 쓰레기 많은 region들 선택 (Garbage First와 비슷)

3. Concurrent Relocation
   - Collection set의 객체들을 새 region으로 복사
   - Mutator 진행 — 옛 ptr 읽으면 LRB가 새 ptr 반환

4. Concurrent Remap (다음 cycle)
   - 옛 ptr들을 새 ptr로 갱신 (lazy)
   - mutator의 LRB가 점진적으로 처리
```

---

## 3. 가지 ③: Shenandoah — Brooks Pointer에서 LRB로

### 3.1 핵심 질문

> "Shenandoah의 Brooks Pointer가 무엇이고, 왜 LRB로 바뀌었나요?"

### 3.2 키워드 1 — Brooks Pointer (옛, JDK 12~14)

```
객체 헤더에 forwarding pointer 추가 (8 byte):
   [object header][brooks_pointer][object data]
                    ↑
                    이 객체의 현재 위치를 가리킴
                    (자기 자신을 가리키거나, 새 위치를 가리킴)

mutator의 모든 객체 접근이 Brooks pointer를 한 번 거침:
   real_ptr = brooks_pointer(obj);
   real_ptr->field

비용:
   - 객체당 8 byte 추가 (메모리 footprint ↑)
   - Indirection 1번 (CPU cache miss 가능)
```

### 3.3 키워드 2 — LRB (JDK 15+, 표준 헤더로 회귀)

```
Brooks 제거하고 ZGC와 유사한 LRB:
   x = obj.field;
   ↓ JIT inline
   raw = obj.field;
   if (in_collection_set(raw)) {   // 이 객체가 evacuation 중?
       raw = lrb_evacuate_or_forward(raw);
   }
   x = raw;

→ 객체 헤더에 추가 byte 없음
→ ZGC 스타일과 수렴
```

### 3.4 키워드 3 — ZGC vs Shenandoah Side-by-side

| | ZGC | Shenandoah |
|---|---|---|
| Author | Oracle | Red Hat |
| 첫 stable | JDK 15 | JDK 15 |
| Generational | JDK 21+ | 미지원 (single-gen) |
| Heap 한계 | 16TB | 수십~수백 GB |
| Pointer | Colored (64-bit) | 표준 |
| Memory model | Multi-mapping | 표준 mmap |
| 객체 헤더 | 표준 | 표준 (LRB 시대) |
| Barrier | Load (Read) | Load (Read) |
| STW pause | < 1ms (보통 ~0.1ms) | ~10ms |
| OS 의존 | Linux/Mac/Windows 일부 | 더 portable |
| 옵션 | -XX:+UseZGC | -XX:+UseShenandoahGC |

**핵심 차이**:
- ZGC가 더 정교 (Colored pointer로 1 instruction check).
- Shenandoah가 더 portable (Multi-mapping 의존 없음).
- JDK 21+에서 둘 다 LRB 기반으로 수렴 중.

---

## 4. 가지 ④: pmap 함정 — 가상 3배, RSS 1배

### 4.1 핵심 질문

> "ZGC 도입 후 메모리 사용량 알람이 3배로 폭주합니다. 왜?"

### 4.2 키워드 1 — 가상 vs 물리

```
ZGC의 Multi-mapping:
   물리 페이지 1개 → 가상 주소 3개 (marked0/marked1/remapped view)

pmap의 측정:
   가상 주소 공간 합산
   → 1개 물리 페이지를 3번 카운트
   → 실제의 3배 보고

RSS (Resident Set Size):
   실제 물리 메모리 사용
   → 1배 (정확)

cgroup memory.current (container):
   실제 물리 메모리
   → 1배 (정확, container limit 기준)
```

### 4.3 키워드 2 — 모니터링 메트릭 변경

```
[잘못된 메트릭]
pmap -x <pid> | grep total
   → 가상 주소 합산 (3배 인플레이션)
   → 알람 3배 폭주

[올바른 메트릭]
RSS:
   cat /sys/fs/cgroup/memory.current
   ps -o rss <pid>
Prometheus:
   process_resident_memory_bytes
container_memory_working_set_bytes
```

### 4.4 키워드 3 — ZGC 도입 시나리오

```
환경: G1 → ZGC 마이그레이션 후
증상: 모니터링 도구의 memory usage 알람 3배 증가

진단: 알람이 가상 주소 (pmap) 기준이었음
조치: RSS 기준 메트릭으로 변경
   - Prometheus: process_resident_memory_bytes
   - cgroup: memory.current
   - 컨테이너 limit과 비교
```

**시니어 관점**: ZGC 도입 전 모니터링 시스템 검토는 필수. 가상 메모리 알람은 끄거나 임계값 조정.

---

## 5. 가지 ⑤: 선택 기준 — Heap / JDK / Portability

### 5.1 핵심 질문

> "ZGC와 Shenandoah 중 무엇을 선택해야 하나요?"

### 5.2 키워드 1 — Heap 크기 기준

```
Heap 크기별 가이드:
   ~32GB:   G1 또는 ZGC/Shenandoah (선택 자유)
   32~128GB: ZGC 권장 (latency 일정)
   128GB+:   ZGC 거의 필수 (Heap 한계 16TB, multi-mapping 효율)
```

### 5.3 키워드 2 — JDK 버전 기준

```
JDK 11~14: ZGC experimental, Shenandoah experimental
JDK 15+:   둘 다 production-ready
JDK 21+:   Generational ZGC 도입 (성능 ↑) — [05. Generational ZGC](./05-generational-zgc.md)
JDK 23+:   Generational ZGC stable
```

### 5.4 키워드 3 — 운영 portability 기준

```
ZGC:
   + 안정적 (Oracle 지원)
   + 큰 Heap
   - pmap 3배 함정 (모니터링 도구 학습 필요)
   - 일부 OS 미지원 (예전엔 Linux 위주)

Shenandoah:
   + Portable (Multi-mapping 의존 없음)
   + Brooks → LRB 진화 완료
   - Generational 없음 (JDK 21 기준)
   - Throughput G1 대비 낮음
```

### 5.5 Throughput vs Latency 비교

| | G1 | ZGC | Shenandoah |
|---|---|---|---|
| Throughput | 100% (기준) | 85~95% (Generational 100%) | 85~95% |
| P99 latency | 50~200ms | <1ms | ~10ms |
| Heap 한계 | ~수십GB | 16TB | ~수백GB |
| 적합 | 일반 서비스 | latency-critical 큰 Heap | latency-critical |

### 5.6 HotSpot 내부 (참고)

**ZGC 진입** (`src/hotspot/share/gc/z/zCollectedHeap.cpp`):
```cpp
class ZCollectedHeap : public CollectedHeap {
    ZHeap* _heap;

    void collect(GCCause::Cause cause) override {
        _heap->mark_start();
        _heap->mark_concurrent();   // mutator와 동시
        _heap->mark_end();           // 짧은 STW
        _heap->relocate_start();
        _heap->relocate_concurrent();   // mutator와 동시
        _heap->relocate_end();
    }
};
```

**LRB 구현** (`src/hotspot/share/gc/z/zBarrier.cpp`):
```cpp
oop ZBarrier::load_barrier_on_oop_field(oop* p) {
    oop o = *p;
    if (z_check_color(o)) {
        return o;   // fast path
    }
    return load_barrier_slow_path(p, o);   // GC 보조 호출
}
```

JIT이 이걸 inline해 매 oop load에 삽입.

---

## 6. 면접 답변 워크플로우

### 6.1 질문 → 가지 매핑

| 면접 질문 | 진입 가지 | 인접 확장 |
|---|---|---|
| "ZGC가 어떻게 sub-ms STW를 달성?" | ① Concurrent Evacuation | Read Barrier |
| "Colored Pointer가 뭔가?" | ② ZGC 메커니즘 | Multi-mapping |
| "Shenandoah Brooks Pointer?" | ③ Shenandoah | LRB 진화 |
| "ZGC vs Shenandoah?" | ⑤ 선택 기준 | side-by-side 표 |
| "ZGC 도입 후 알람 3배?" | ④ pmap 함정 | RSS 메트릭 |
| "Read Barrier 비용?" | ① Concurrent Evacuation | trade-off |
| "마이그레이션 검토?" | ⑤ 선택 기준 | 단계별 |

### 6.2 답변 템플릿

예: "ZGC의 Colored Pointer가 무엇이고 왜 효과적인가요?"

> "ZGC는 Colored Pointer + Multi-mapping + LRB로 sub-ms STW를 달성합니다 (← 루트).
> Colored Pointer는 가지 ②의 핵심.
> 첫째, **64-bit pointer의 고위 비트에 GC state (marked0/1, remapped) 인코딩**.
> 둘째, **별도 mark bitmap 불필요** — pointer 자체에 정보.
> 셋째, **GC state check가 1 instruction** (mask + cmp).
> 더해서 Multi-mapping과 결합 — 같은 물리 페이지를 3개 가상 view (marked0/marked1/remapped)에 mapping. State 비트가 어느 view 통해 접근할지 결정. 이게 가지 ④의 pmap 함정의 원인이기도 합니다 (→ 가상 3배 보고)."

---

## 7. 꼬리질문 트리

### Q1 [가지 ②]. ZGC의 Colored Pointer가 무엇이고 왜 효과적인가요?

> 64-bit pointer의 고위 비트에 GC state (marked0/1, remapped 등) 인코딩.
> 효과:
> - Pointer 자체에 정보 → 별도 mark bitmap 불필요.
> - GC state check가 1 instruction (mask + cmp).
> - Concurrent evacuation 시 mutator가 정확한 state 즉시 확인.

### Q2 [가지 ②+④]. Multi-mapping의 동작과 pmap 함정은?

> 한 물리 페이지를 3개 가상 주소에 mapping. Colored pointer의 state 비트로 어느 view 사용할지 결정.
>
> 운영 함정: `pmap`은 가상 주소 합산 → RSS의 3배 보고. 실제 물리 메모리는 1배.
>
> → 모니터링 메트릭은 RSS 기준 (`/sys/fs/cgroup/memory.current` 또는 `process_resident_memory_bytes`).

**🪝 Q2-1: Container limit이 RSS인가 가상인가?**
> RSS 기준. cgroup memory.current가 container limit과 비교 대상. ZGC의 가상 3배는 limit에 무관.

### Q3 [가지 ①]. Read Barrier의 비용은?

> 매 ref 읽기에 추가 instruction 2~5개.
> 일반 워크로드 throughput ~2~5% 영향.
> Latency 가치 (sub-ms STW) 대비 매우 작은 비용.

**🪝 Q3-1: 그럼 Write Barrier도 같이 쓰나?**
> ZGC도 Write Barrier 사용 (concurrent marking 정확성). Read Barrier는 concurrent evacuation 추가 메커니즘. 둘 다 함께 동작.

### Q4 [가지 ③]. Shenandoah의 Brooks Pointer가 왜 LRB로 바뀌었나?

> Brooks (JDK 12~14): 객체 헤더에 8 byte forwarding pointer. 메모리 footprint ↑, indirection 1번 (cache miss).
> LRB (JDK 15+): 표준 헤더로 회귀. ZGC와 유사한 방식.
> → 더 효율 + 표준 객체 모델과 호환.

### Q5 [가지 ⑤]. ZGC와 Shenandoah 선택 기준은?

> - Heap 크기 ~32GB: 둘 다 OK.
> - Heap 32GB+: ZGC 권장.
> - Heap 100GB+: ZGC 거의 필수.
> - Generational 활용 (JDK 21+): Generational ZGC.
> - 운영 portability: Shenandoah.

### Q6 (Killer) [가지 ⑤]. G1 → ZGC 마이그레이션을 검토 중입니다. 무엇을 확인해야 하나요?

> 1. **Heap 크기**: ZGC가 효과 있는 임계 (32GB+).
> 2. **JDK 버전**: 21+ 권장 (Generational ZGC).
> 3. **OS 지원**: Linux/Mac/Windows ZGC 호환 확인.
> 4. **메트릭 변경**: RSS 기준 (pmap 3배 함정 회피).
> 5. **벤치마크**: JMH로 throughput/latency 측정.
> 6. **운영 변화**: GC log 형식 다름 (학습 비용).
> 7. **Read barrier 비용**: hot path 성능 영향 측정.
> 8. **Container memory**: 가상은 3배지만 RSS는 1배 — limit은 RSS로.
> 9. **단계적 도입**: canary 1대로 시작, 모니터링 안정 후 확대.

---

## 8. 학습 체크리스트

- [ ] 0장 마인드맵을 1분 이내로 그릴 수 있다
- [ ] 가지 ①: STW Evacuation의 정확성 보장 → Concurrent에서 Read Barrier로 해결을 설명한다
- [ ] 가지 ②: Colored Pointer의 state 비트 인코딩을 그린다
- [ ] 가지 ②: Multi-mapping의 3 view를 그린다 (물리 1, 가상 3)
- [ ] 가지 ②: LRB의 fast path / slow path 코드를 적는다
- [ ] 가지 ③: Brooks Pointer (객체당 8B) vs LRB (표준 헤더) 차이를 설명한다
- [ ] 가지 ③: ZGC vs Shenandoah side-by-side 표를 그린다
- [ ] 가지 ④: pmap 가상 3배 vs RSS 1배 함정을 설명한다
- [ ] 가지 ④: 올바른 메트릭 (cgroup memory.current, process_resident_memory_bytes)을 인용한다
- [ ] 가지 ⑤: Heap 크기 / JDK / portability 3축 선택 가이드를 말한다
- [ ] 7장 꼬리질문 6개에 답한다

---

## 다음 단계

- → [05. Generational ZGC](./05-generational-zgc.md): ZGC + Young/Old 분할
- ← [03. CMS and G1](./03-cms-and-g1.md)

## 참고

- **JEP 333 — ZGC**: https://openjdk.org/jeps/333
- **JEP 189 — Shenandoah**: https://openjdk.org/jeps/189
- **Per Liden ZGC talks**: JavaOne/Devoxx 2018+
- **HotSpot `zCollectedHeap.cpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/gc/z/zCollectedHeap.cpp
- **HotSpot `zBarrier.cpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/gc/z/zBarrier.cpp
