# 04-01. GC Fundamentals — Reachability + 3가지 회수 변환

> GC 알고리즘은 30년간 진화했지만 본질은 두 질문에 답하는 것이다. **"무엇이 살아있는가"** + **"죽은 것을 어떻게 회수하는가"**.
> 답은 30년째 같다. Reachability로 살아있음을 정의하고, Mark-Sweep / Mark-Compact / Copying 세 가지 변환으로 회수한다.
> Serial부터 Generational ZGC까지의 진화는 본질의 변화가 아니라 **"STW를 어떻게 줄였나"의 변천사**다.

---

## 이 문서의 사용법

이 문서는 **면접용 마인드맵**을 따라 선형으로 펼친 구조다. 학습 순서 = 면접 답변 순서 = 백지에 그리는 순서.

1. **0장 마인드맵을 먼저 외운다** — 루트 한 문장 + 5가지 가지 + 각 가지의 키워드 3개.
2. **1~5장을 순서대로 학습한다** — 각 장이 마인드맵의 한 가지에 정확히 대응.
3. **6장 면접 워크플로우로 검증** — 질문을 보면 어느 가지로 가야 하는지 매핑.
4. **7장 꼬리질문으로 깊이 점검**.

---

## 0. 마인드맵 — 면접 종이에 그릴 그림

### 루트 한 문장 (anchor)

> **"GC는 GC Roots에서 도달 가능한 객체만 살리고, 3가지 회수 변환(Mark-Sweep/Compact/Copying)으로 죽은 메모리를 거둔다. 30년 진화는 STW 축소의 역사다."**

이 한 문장에서 모든 답변이 출발한다. 어떤 질문이 와도 이 문장부터 말하고 적절한 가지로 분기.

### 5개 가지 — 순서를 외운다

```
                  [ROOT: Reachability + 3 변환 + STW 축소]
                                   │
       ┌─────────┬──────────────────┼──────────────────┬─────────┐
       │         │                  │                  │         │
      ① 살아있음  ② 회수 변환        ③ Generational   ④ Mutator  ⑤ STW
   (Reachability)(M-S/M-C/Copy)    Hypothesis        협력 메커니즘  진화
       │         │                  │                  │         │
       │    ┌────┼────┐         ┌───┼───┐         ┌────┼────┐    │
    GC Roots Mark-Sweep         단명 객체           Write       Safepoint
     4종    Mark-Compact         95%                Barrier      polling
   ref count Copying            Card Table         Read         Concurrent
    한계     trade-off          Young/Old          Barrier      GC 등장
```

### 가지별 핵심 키워드 (각 가지 3개씩만)

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① 살아있음 (Reachability)** | GC Roots 4종 | 순환 참조 해결 | ref count 거부 |
| **② 회수 변환** | Mark-Sweep | Mark-Compact | Copying |
| **③ Generational Hypothesis** | 단명 객체 95% | Young/Old 분할 | live ratio 활용 |
| **④ Mutator 협력** | Write Barrier | Read Barrier | Card Table |
| **⑤ STW 진화** | Safepoint | Concurrent | 30년 축소사 |

### 면접 답변 흐름

> 면접관 질문 → 루트 문장 → 질문에 맞는 가지 1개 선택 → 그 가지의 키워드 3개 순서대로 설명 → 듣는 사람의 관심에 따라 인접 가지로 확장

---

## 1. 가지 ①: 살아있음 — Reachability가 GC의 정의

### 1.1 핵심 질문

> "GC는 어떻게 '이 객체는 살아있다'를 판단하나요? 왜 reference counting이 아닌가요?"

### 1.2 키워드 1 — GC Roots 4종

```
[GC Roots — Reachability 분석의 시작점]

1. Stack 기반 (per-thread):
   - JVM Stack의 local variable slot 안 oop
   - Operand Stack 안 oop
   - OopMap이 어느 slot이 oop인지 표시

2. Class 기반 (shared):
   - InstanceKlass의 static field
   - String pool (interned String)
   - Symbol table

3. Native 기반:
   - JNI Global Reference (NewGlobalRef)
   - JNI Weak Reference

4. Thread/Monitor 기반:
   - Active thread의 ContextClassLoader
   - synchronized 잡힌 객체
   - ThreadLocal
```

이 4종에서 출발해 참조를 따라 도달 가능한 객체 = **reachable = 살아있음**. 나머지는 dead.

### 1.3 키워드 2 — 순환 참조 해결

```
객체 A → 객체 B → 객체 A (서로 가리킴)
   ↑
   GC Roots 어디에서도 안 가리킴

Reference Counting (Python, Swift):
   A의 count = 1 (B가 가리킴)
   B의 count = 1 (A가 가리킴)
   → 둘 다 count > 0 → 회수 안 됨 (누수)

Reachability (Java, Go):
   GC Roots에서 따라가도 A, B 도달 불가
   → 둘 다 dead → 회수
```

이게 Java가 reachability를 선택한 가장 큰 이유.

### 1.4 키워드 3 — Reference Counting 거부의 이유

| | Reference Counting | Reachability |
|---|---|---|
| 순환 참조 | 못 회수 | 회수 가능 |
| Mutator overhead | 매 ref 변경마다 count 갱신 | Write barrier만 |
| Thread-safe | atomic 증감 필수 | barrier 단순 |
| 회수 시점 | 즉시 (count=0) | 주기적 GC cycle |
| STW | 없음 | 있음 (또는 concurrent) |

→ Java는 멀티스레드 친화 + 순환 참조 회수를 위해 **reachability + 주기적 GC + STW**를 선택. 대가는 STW 비용 — 30년간 이 비용을 줄여온 것이 GC 진화사.

### 1.5 Mark Phase 알고리즘

```
1. GC Roots 모두 식별 (스레드 stack scan 등)
2. Roots를 worklist에 enqueue
3. while worklist not empty:
     obj = worklist.pop()
     if not obj.marked:
         obj.marked = true
         for each ref in obj.fields:
             worklist.push(ref)
4. 끝나면: marked = 살아있음, !marked = 죽음
```

**마킹 시간 ≈ 살아있는 객체 수에 비례** — live ratio가 GC 비용의 핵심.

---

## 2. 가지 ②: 회수 변환 — 3가지의 차이

### 2.1 핵심 질문

> "죽은 객체를 어떻게 회수하나요? 왜 GC마다 다른 알고리즘을 쓰나요?"

### 2.2 키워드 1 — Mark-Sweep

```
GC 전:  [살][죽][살][죽][살]
        ↓ Mark (reachable 표시)
        ↓ Sweep (dead를 free list에 반환)
GC 후:  [살][free][살][free][살]

특징:
   + 빠름 (객체 이동 없음)
   + 단순
   - Fragmentation (free 공간 흩어짐)
   - 큰 객체 할당 시 free 못 찾을 수 있음 → Full GC

적용: 옛 CMS Old gen
```

### 2.3 키워드 2 — Mark-Compact

```
GC 전:  [살][죽][살][죽][살]
        ↓ Mark
        ↓ Compact (살아있는 객체를 한쪽으로 이동)
GC 후:  [살][살][살][free][free]

특징:
   + Fragmentation 0
   + 큰 객체 할당 안전
   - 객체 이동 비용 큼 (memcpy)
   - 모든 ref 갱신 필요

적용: Serial Old, Parallel Old, G1 Full GC
```

### 2.4 키워드 3 — Copying

```
GC 전:
   영역 A: [살][죽][살][죽][살]   ← active (from-space)
   영역 B: (empty)                  ← inactive (to-space)
        ↓ Mark + Copy 동시
GC 후:
   영역 A: (empty)
   영역 B: [살][살][살]              ← 다음 GC의 from-space

특징:
   + 매우 빠름 (live ratio 낮을 때)
   + Fragmentation 0
   - 메모리 2배 필요 (두 영역)
   - live ratio 높으면 비효율

적용: 모든 Young GC (Eden + Survivor)
```

### 2.5 3가지 비교 표

| | Mark-Sweep | Mark-Compact | Copying |
|---|---|---|---|
| 속도 | 빠름 | 느림 (이동 비용) | 매우 빠름 (low live ratio) |
| Fragmentation | 있음 | 없음 | 없음 |
| 메모리 사용 | 100% | 100% | 50% (두 영역) |
| Live ratio 적합 | 모든 | 모든 | 낮을수록 좋음 |
| 적용 영역 | 옛 CMS Old | Serial/Parallel Old, G1 Full | 모든 Young |

### 2.6 한 GC = 영역별 변환 조합

```
Serial GC:
   Young = Copying
   Old   = Mark-Compact

Parallel GC:
   Young = Copying (multi-thread)
   Old   = Mark-Compact (multi-thread)

CMS:
   Young = Copying
   Old   = Mark-Sweep (compact 없음 → fragmentation)

G1:
   모든 region에서 Evacuation (Copying의 일반화)
   Full GC만 Mark-Compact

ZGC / Shenandoah:
   Concurrent Mark + Concurrent Evacuation (Copying)
```

→ **모든 GC는 이 3가지의 조합이다**. Mark-Sweep만 쓰는 GC도, Copying만 쓰는 GC도 없음. 영역별 live ratio에 맞춰 다르게 선택.

---

## 3. 가지 ③: Generational Hypothesis — 모든 GC의 출발점

### 3.1 핵심 질문

> "왜 Heap을 Young/Old로 분할하나요? 그 분할이 어떤 효과를 주나요?"

### 3.2 키워드 1 — Weak Generational Hypothesis

> **"대부분의 객체는 일찍 죽는다"** — Lieberman & Hewitt 1983.

실측 데이터:
- 일반 Java 앱 객체의 **80~98%가 첫 Young GC를 못 넘긴다**.
- 그 후 살아남은 객체 중 다시 80%가 다음 GC에서 죽음.
- 결국 ~5%만 Old로 promote.

### 3.3 키워드 2 — Young/Old 분할의 효과

```
[분할 없이 (single-gen)]
매 GC: 전체 Heap mark + 회수
   → live ratio 평균 30~50%
   → Mark + Sweep/Compact 모두 비용 큼

[Young/Old 분할]
Young GC (자주):
   - Young만 처리 (전체의 10~30%)
   - live ratio 5% → 95% 즉시 회수
   - Copying 매우 효율적
   - 빈도: 수 초마다, ~10~50ms

Old GC (가끔):
   - Old 처리 (live ratio 80%+)
   - Copying 비효율 → Mark-Compact 사용
   - 빈도: 수 분~수 시간마다, ~수백 ms ~ 수 초

→ 같은 메모리 회수량에 GC 비용 1/5~1/10
```

### 3.4 키워드 3 — Live ratio가 모든 것을 결정

```
Young (live ratio ~5%):
   → Copying이 최적 (5% 복사하면 95% 회수)

Old (live ratio ~80%):
   → Copying 비효율 (80% 복사 비용)
   → Mark-Compact가 적합 (살아있는 거 압축)

→ "어디는 Copying, 어디는 Mark-Compact"의 선택은
   live ratio 차이에서 자동 도출
```

### 3.5 분할의 대가 — Cross-generation 참조 추적

```
Young GC 시 Old 전체를 scan하면 효율 0
   → Young만 scan하고 싶음
   
그러나 Old → Young 참조가 있으면 Y는 살아있어야:
   Old gen 객체 O가 Young gen 객체 Y를 가리킴
   → Y는 reachable
   → Y를 살려야 함
   → 그러나 O는 어떻게 알지?

해결: Card Table
   - Heap을 512B 카드로 나눔
   - Old의 어느 카드가 Young 참조를 가지면 dirty 표시
   - Young GC 시 dirty card만 scan (Old 전체 안 봄)
```

→ Card Table은 **Generational의 필수 부속**. 자세히는 [Chapter 02-06 GC bookkeeping](../02-runtime-data-areas/06-gc-bookkeeping-and-others.md).

---

## 4. 가지 ④: Mutator 협력 — Write Barrier / Read Barrier

### 4.1 핵심 질문

> "GC가 mutator(application thread)와 어떻게 협력하나요? 그 비용은?"

### 4.2 키워드 1 — Write Barrier

```
Java 코드: obj.field = newRef;
   ↓ JIT가 inline
실제 실행:
   1. (pre-barrier) GC 작업 (SATB 등)
   2. obj.field = newRef   ← 원래 store
   3. (post-barrier) Card Table 갱신, dirty queue 등

비용: 일반 워크로드 ~5~10% throughput 영향
```

**역할**:
- **Card Table dirty 마킹** — Old → Young 참조 추적.
- **SATB queue** (G1, ZGC) — concurrent marking 중 변경 추적.
- **Cross-region tracking** (G1 RSet).
- **Concurrent GC의 정확성 보장**.

### 4.3 키워드 2 — Read Barrier (ZGC/Shenandoah)

```
Java 코드: x = obj.field;
   ↓ JIT가 inline (ZGC LRB)
실제 실행:
   raw = obj.field;
   if (raw_color != expected) {
       raw = lrb_slow_path(raw);   // 객체 이동 중이면 새 주소 반환
   }
   x = raw;

비용: ~2~5% throughput
효과: Concurrent Evacuation 가능 (객체 이동 중에도 mutator 진행)
```

→ Read Barrier는 ZGC/Shenandoah의 sub-ms STW의 핵심. 자세히는 [04. ZGC and Shenandoah](./04-zgc-and-shenandoah.md).

### 4.4 키워드 3 — Barrier 비용의 본질

| Barrier 종류 | 사용 GC | 비용 | 이점 |
|---|---|---|---|
| Card Table 갱신 | 모든 generational | ~5% | Young GC 효율 |
| SATB queue | G1, ZGC | ~5% | Concurrent marking 정확성 |
| Load Reference Barrier | ZGC, Shenandoah | ~2~5% | Concurrent evacuation |

**시니어 관점**:
- Barrier는 throughput 비용으로 latency를 산다.
- "Barrier 없음 = throughput 높음, STW 김" (Serial/Parallel).
- "Barrier 많음 = throughput 낮음, STW 짧음" (ZGC/Shenandoah).
- 워크로드에 맞춰 선택.

---

## 5. 가지 ⑤: STW 진화 — Safepoint + Concurrent

### 5.1 핵심 질문

> "왜 STW가 필요한가요? 30년 진화는 어떻게 STW를 줄여왔나요?"

### 5.2 키워드 1 — Safepoint (STW 진입 메커니즘)

```
1. JVM이 polling page를 mprotect(PROT_NONE)으로 변경
2. 인터프리터: 메서드 진입/exit, loop back-edge에 poll instruction
   - polling page 읽기 시도 → SEGV → signal handler → thread 정지
3. JIT 컴파일된 코드: 같은 위치에 poll 삽입
4. 모든 thread가 safepoint에서 자발적 정지 → GC 진행
5. GC 끝나면 polling page를 다시 PROT_READ로 → thread 재개

→ TTSP (Time-To-Safepoint) = 모든 thread가 정지하기까지의 시간
→ TTSP가 길면 실제 STW = GC 시간 + TTSP
```

자세히는 [Chapter 05 Threading](../05-threading/).

### 5.3 키워드 2 — STW 없이 Mark 시도하면?

```
[STW 없는 시나리오]
GC thread: 객체 A를 reachable로 mark
        ↓ 동시에
Mutator: a.field = newObj   ← A의 ref 변경
        ↓
GC thread: A의 ref 따라가서 newObj 발견 못 함
        ↓
잘못 회수 → 메모리 손상 → JVM crash

[STW 적용]
GC 시작 → 모든 thread 정지 → 정확한 mark → 회수 → resume
```

→ **STW는 정확성의 가장 단순한 보장책**. 그러나 모든 thread 정지는 latency 비용 — 30년 진화가 이 비용 축소에 집중.

### 5.4 키워드 3 — 30년 STW 축소사

| 연도 | GC | STW 특성 | 핵심 발상 |
|---|---|---|---|
| 1959 | McCarthy Mark-Sweep | 전체 Heap STW | GC 자체의 시작 |
| 1969 | Cheney Copying | 전체 Heap STW | 살아있는 객체만 복사 |
| 1996 | JDK 1.0 Serial | 단일 thread STW | Java GC의 시작 |
| 2002 | Parallel GC | Multi-thread STW (짧아짐) | 멀티코어 활용 |
| 2002 | CMS | Concurrent Mark, STW는 Sweep만 | 첫 concurrent |
| 2009 | G1 (experimental) | Region 단위 STW (예측 가능) | region 기반 |
| 2018 | ZGC (experimental) | sub-ms STW | Colored pointer + Read Barrier |
| 2023 | Generational ZGC | sub-ms STW + G1 동등 throughput | Generational + ZGC |

**핵심 통찰**: 30년 동안 본질 (Reachability + 3 변환)은 안 바뀜. **STW 축소만**이 진화의 축.

```
Serial (1996):       [─────── STW ───────] ← 전체
Parallel (2002):     [── STW ──]            ← 짧아짐 (multi-thread)
CMS (2002):          [STW] ... [STW] ...    ← Mark는 concurrent
G1 (2009):           [── STW (예측 가능) ──] ← region 수 조정
ZGC (2018):          [STW] ...              ← sub-ms
Gen ZGC (2023):      [STW] ...              ← sub-ms + throughput
```

---

## 6. 면접 답변 워크플로우

### 6.1 질문 → 가지 매핑

| 면접 질문 | 진입 가지 | 인접 확장 |
|---|---|---|
| "GC가 어떻게 살아있는 객체를 판단?" | ① Reachability | GC Roots 4종 |
| "순환 참조는 어떻게 처리?" | ① Reachability | ref count 한계 |
| "Mark-Sweep과 Copying 차이?" | ② 회수 변환 | live ratio |
| "왜 Young/Old로 나누나?" | ③ Generational | Hypothesis 실측 |
| "Card Table이 뭔가요?" | ③ Generational | ④ Write Barrier |
| "Write Barrier 비용은?" | ④ Mutator 협력 | concurrent GC |
| "왜 STW가 필요?" | ⑤ STW | safepoint |
| "30년 GC 진화 요약?" | ⑤ STW | 축소사 표 |

### 6.2 답변 템플릿

> **루트 문장 한 줄 → 해당 가지 키워드 3개 순서대로 → 듣는 사람 표정 보고 인접 가지로**

예: "Java GC가 reference counting을 안 쓰는 이유는?"

> "GC는 GC Roots에서 도달 가능한 객체만 살리는 reachability 기반입니다 (← 루트).
> Reference counting을 거부한 이유는 가지 ①에 있습니다.
> 첫째, **순환 참조 문제**. A→B→A 둘 다 count > 0이라 누수.
> 둘째, **mutator overhead**. 매 ref 변경마다 count 갱신, 멀티스레드면 atomic 증감 필요.
> 셋째, **회수 시점 trade-off**. 즉시성을 얻는 대신 매 store에 count 비용.
> Java는 멀티스레드 친화 + 순환 회수를 위해 reachability + 주기적 GC + STW를 선택. 대가가 STW 비용이고, 30년 진화가 그 축소사입니다 (→ 가지 ⑤로 자연 연결)."

---

## 7. 꼬리질문 트리 (가지별)

### Q1 [가지 ①]. Java GC가 reference counting 안 쓰는 이유는?

> 1. 순환 참조 못 회수 (a→b→a 둘 다 count > 0).
> 2. ref 변경 시마다 count 갱신 → mutator overhead.
> 3. Thread-safe atomic 증감 비용.
> Reachability는 이 모두를 회피. 대가는 STW (또는 concurrent).

**🪝 Q1-1: GC Roots는 정확히 어떤 게 있나요?**
> 4종. Stack 기반 (local/operand의 oop), Class 기반 (static field, String pool), Native 기반 (JNI global ref), Thread/Monitor 기반 (ContextClassLoader, synchronized).

### Q2 [가지 ②]. Mark-Sweep, Mark-Compact, Copying의 차이는?

> Mark-Sweep: 빠르고 단순. 단점 fragmentation.
> Mark-Compact: fragmentation 0. 단점 객체 이동 비용.
> Copying: live ratio 낮을 때 매우 빠름. 단점 메모리 2배 사용.
> 한 GC는 영역별로 다른 변환 조합 — 예: Serial은 Young Copying + Old Mark-Compact.

**🪝 Q2-1: Copying이 Young에 적합한 이유는?**
> Young의 live ratio가 ~5%. 살아있는 객체만 복사하면 95%의 메모리를 즉시 회수. 이게 Copying의 효율이 극대화되는 조건.

### Q3 [가지 ③]. Weak Generational Hypothesis가 무엇이고 왜 GC 설계의 기반인가?

> "대부분 객체는 일찍 죽는다" — Lieberman & Hewitt 1983. 실측 80~98% 객체가 첫 Young GC를 못 넘김.
> 효과: Young만 자주 청소 (live ratio 5% → 95% 즉시 회수). Old는 가끔 (live ratio 80%, Mark-Compact).
> 같은 회수량에 GC 비용 1/5~1/10.

**🪝 Q3-1: 분할의 대가는?**
> Cross-generation 참조 추적 — Old → Young 참조가 있으면 Young은 살려야 함. Card Table로 해결 (Old의 dirty card만 scan).

### Q4 [가지 ④]. Write Barrier가 무엇이고 왜 필요한가요?

> Mutator의 ref 쓰기에 추가되는 GC 협력 코드. 역할: Card Table 갱신 (Old→Young 추적), SATB queue (concurrent marking), G1 RSet 갱신.
> 비용: 일반 ~5~10% throughput. Concurrent GC의 전제.

**🪝 Q4-1: Read Barrier는 언제 필요?**
> Concurrent Evacuation (객체 이동 중 mutator 진행). ZGC의 LRB가 대표. Mutator가 옛 주소 읽을 때 새 주소로 redirect. 비용 ~2~5%.

### Q5 [가지 ⑤]. STW가 왜 필요한가요?

> Mutator가 mark 중 객체 그래프 변경 시 incorrect mark → 잘못 회수 → 메모리 손상.
> STW가 정확성의 가장 단순한 보장책. 모든 thread 정지 → 정확한 snapshot.
> 그러나 latency 비용 → concurrent GC가 SATB/IU로 정확성 유지하며 STW 줄임.

**🪝 Q5-1: Safepoint가 어떻게 동작?**
> polling page를 PROT_NONE으로 변경. 모든 thread가 메서드 진입/loop back-edge에서 polling page 읽기 시도 → SEGV → signal handler → 자발적 정지. 모든 thread 정지하기까지 시간 = TTSP.

### Q6 (Killer) [가지 ⑤]. 30년 GC 진화를 한 문장으로 요약하면?

> 본질 (Reachability + 3 변환)은 1959년부터 그대로. **진화는 STW를 어떻게 줄였나의 역사**.
> Serial → Parallel (multi-thread STW), Parallel → CMS (concurrent Mark), CMS → G1 (region 단위 예측 가능), G1 → ZGC (sub-ms via colored pointer + Read Barrier), ZGC → Generational ZGC (G1 동등 throughput + sub-ms).
> 각 단계의 대가: throughput 일부 손실 또는 메모리 footprint 증가.

---

## 8. 학습 체크리스트

면접 전 백지에서 다음을 다 해낼 수 있어야 마스터:

- [ ] 0장 마인드맵을 종이에 1분 이내로 그릴 수 있다 (루트 + 5가지 + 각 키워드 3개)
- [ ] 가지 ①: GC Roots 4종을 외운다 (Stack/Class/Native/Thread)
- [ ] 가지 ①: ref count의 3가지 한계 (순환참조, overhead, atomic 비용)를 말한다
- [ ] 가지 ②: 3가지 변환을 그림으로 그리고 trade-off 표를 적는다
- [ ] 가지 ②: "한 GC = 영역별 변환 조합" 원칙으로 Serial/CMS/G1을 분해한다
- [ ] 가지 ③: Weak Generational Hypothesis와 실측 수치 (80~98%)를 인용한다
- [ ] 가지 ③: Card Table이 generational의 필수 부속임을 설명한다
- [ ] 가지 ④: Write Barrier의 3가지 역할 (Card, SATB, RSet)을 말한다
- [ ] 가지 ④: Read Barrier가 Concurrent Evacuation의 핵심임을 설명한다
- [ ] 가지 ⑤: Safepoint polling 메커니즘을 그린다
- [ ] 가지 ⑤: 30년 진화 표 (Serial→Gen ZGC)를 STW 축소 관점으로 정리한다
- [ ] 7장 꼬리질문 6개에 막힘없이 답한다

---

## 다음 단계

- → [02. Generational + Serial/Parallel](./02-generational-and-serial-parallel.md): 가지 ③의 첫 구현
- → [03. CMS and G1](./03-cms-and-g1.md): 가지 ⑤의 region 진화
- → [04. ZGC and Shenandoah](./04-zgc-and-shenandoah.md): 가지 ④의 Read Barrier
- → [05. Generational ZGC](./05-generational-zgc.md): 가지 ③ + ⑤의 결합
- → [06. GC Tuning and Ops](./06-gc-tuning-and-ops.md): 운영 종합
- ← [Chapter 02-06 GC Bookkeeping](../02-runtime-data-areas/06-gc-bookkeeping-and-others.md)

## 참고

- **Lieberman & Hewitt (1983) — Generational GC**: "A Real-Time Garbage Collector Based on the Lifetimes of Objects"
- **JLS §12.6 (Finalization)**: https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html
- **HotSpot `collectedHeap.hpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/gc/shared/collectedHeap.hpp
- **HotSpot `g1BarrierSet.cpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/gc/g1/g1BarrierSet.cpp
- **Oracle GC Tuning Guide (JDK 21)**: https://docs.oracle.com/en/java/javase/21/gctuning/
