# 04-03. CMS (제거됨) → G1 — Region 기반의 진화

> 2002년 CMS는 **첫 concurrent GC**로 latency 시대를 열었다. 그러나 fragmentation + Concurrent Mode Failure의 본질적 한계로 JDK 14에서 제거됐다.
> G1은 그 자리를 차지한 후속 — **region 기반**으로 fragmentation 해결 + **예측 가능한 STW 목표**.
> 시니어가 알아야 할 것: CMS는 운영에서 거의 안 보이지만 옛 사고의 흔적이 남아 있다. G1은 현재 default GC — 모든 운영자가 알아야.

---

## 이 문서의 사용법

1. **0장 마인드맵을 먼저 외운다** — 루트 한 문장 + 5가지 가지 + 키워드 3개.
2. **1~5장을 순서대로 학습한다**.
3. **6장 면접 워크플로우** + **7장 꼬리질문**.

---

## 0. 마인드맵 — 면접 종이에 그릴 그림

### 루트 한 문장 (anchor)

> **"CMS는 Old를 concurrent하게 Mark-Sweep하지만 compact 안 해서 fragmentation으로 죽었다. G1은 Heap을 region으로 나누고 garbage-rich region부터 evacuate하며 STW를 목표 안에 맞춘다."**

### 5개 가지 — 순서를 외운다

```
              [ROOT: CMS의 한계 → G1의 region 기반 + pause prediction]
                                  │
       ┌─────────┬──────────────────┼──────────────────┬─────────┐
       │         │                  │                  │         │
      ① CMS    ② CMS의 한계        ③ G1 region        ④ G1 GC 종류 ⑤ Pause
   6 phase   (제거 이유)          (Heap 분할)         (Young/Mixed/Full) Prediction
       │         │                  │                  │         │
   ┌───┼───┐  ┌──┼──┐           ┌───┼───┐         ┌────┼────┐
  Init  Conc  Frag  CMF         2048   Humongous  Concurrent  Mixed
  Mark  Mark  CPU   Float       region  Object    Marking     GC
  Remark Sweep Maint Garbage    1~32MB  RSet       SATB
```

### 가지별 핵심 키워드

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① CMS 6 phase** | Initial Mark / Conc Mark | Remark | Conc Sweep |
| **② CMS 한계** | Fragmentation | Concurrent Mode Failure | Floating Garbage |
| **③ G1 region** | 2048 region 가이드 | 동적 역할 변경 | Humongous |
| **④ G1 GC 종류** | Young GC | Mixed GC | Full GC (사고) |
| **⑤ Pause Prediction** | MaxGCPauseMillis | 통계 기반 | region 수 조정 |

### 면접 답변 흐름

> 면접관 질문 → 루트 문장 → 해당 가지 → 키워드 3개 → 인접 가지로 확장

---

## 1. 가지 ①: CMS — 첫 Concurrent GC의 6 phase

### 1.1 핵심 질문

> "CMS의 6 phase는 무엇이고, 그 중 어디가 STW고 어디가 concurrent인가요?"

### 1.2 키워드 1 — STW phase (Initial Mark + Remark)

```
1. Initial Mark (STW, ~수 ms)
   - GC Roots만 mark (stack/static/JNI)
   - 매우 짧음

4. Remark (STW, ~수십 ms)
   - Concurrent Mark 중 mutator의 변경분 일괄 처리
   - 정확한 마킹 완료
```

→ STW는 2번만 있고 각각 짧음. 이게 CMS의 핵심 약속.

### 1.3 키워드 2 — Concurrent phase (Mark + Sweep)

```
2. Concurrent Mark (concurrent, ~수 초)
   - reachable 객체 mark
   - mutator와 동시 동작
   - mutator의 ref 변경은 별도 queue에 기록

3. Concurrent Preclean (concurrent)
   - Incremental update queue 처리
   - mutator 변경분 일부 미리 처리 (Remark STW 단축)

5. Concurrent Sweep (concurrent)
   - 죽은 객체 → free list 반환
   - ★ compact 없음 — fragmentation 누적

6. Concurrent Reset
   - 다음 cycle 준비
```

### 1.4 키워드 3 — Mutator 변경 추적 (Incremental Update)

```
Concurrent Mark 중 문제:
   GC thread: 객체 A를 mark 중
   동시에 Mutator: a.field = newObj
   → GC가 newObj를 못 찾을 수 있음

CMS의 해결: Incremental Update
   - Write barrier가 변경된 카드를 dirty 표시
   - Remark phase에서 dirty card scan
   - newObj를 mark에 포함
```

→ Write barrier는 모든 generational GC에 있지만, CMS는 추가로 IU queue 관리.

---

## 2. 가지 ②: CMS의 한계 — 왜 제거됐나

### 2.1 핵심 질문

> "왜 CMS가 JDK 14에서 제거됐나요?"

### 2.2 키워드 1 — Fragmentation (가장 큰 문제)

```
CMS는 Mark-Sweep만 — compact 안 함.
시간 지나면 Old gen에 작은 free 영역이 흩어짐:
   [살][free 4B][살][free 8B][살][free 16B][살]

큰 객체 할당 (예: 1MB):
   → 연속된 1MB free 영역 없음
   → 할당 실패
   → 응급 Full GC (compact 위해, STW 매우 김)
```

**시니어 시점**: CMS Full GC = 운영 사고. STW 수 초~수십 초.

### 2.3 키워드 2 — Concurrent Mode Failure

```
Concurrent collecting 진행 중:
   Mutator가 Old를 매우 빠르게 채움
   → GC가 따라가지 못함
   → Old 가득 → 응급 Full GC (STW)

GC log 시그니처:
   "concurrent mode failure"
   "promotion failed"

CMS 운영 사고의 가장 흔한 메시지.
```

### 2.4 키워드 3 — Floating Garbage + CPU 영향

```
Floating Garbage:
   Concurrent mark 중에 죽은 객체
   → mark 시점엔 살아있어서 이번 cycle 회수 못 함
   → 다음 cycle에야 처리
   → 추가 메모리 부담

CPU 영향:
   Concurrent 작업이 mutator와 CPU 경쟁
   → Throughput 10~20% 손실

유지보수 부담:
   복잡한 코드 (수만 줄)
   새 GC 기능 (Generational ZGC 등) 추가 어려움
```

→ **JEP 363 (JDK 14)** 에서 완전 제거. G1이 대체.

### 2.5 4가지 한계 요약

| 한계 | 원인 | 영향 |
|---|---|---|
| Fragmentation | Mark-Sweep만, compact 없음 | 큰 객체 할당 실패 → 응급 Full GC |
| Concurrent Mode Failure | GC가 mutator 못 따라감 | 응급 Full GC, STW 김 |
| Floating Garbage | Concurrent mark 중 죽은 객체 | 다음 cycle 부담 |
| CPU 영향 | Mutator와 CPU 경쟁 | Throughput 10~20% ↓ |

---

## 3. 가지 ③: G1의 Region — Heap을 작은 조각으로

### 3.1 핵심 질문

> "G1이 Heap을 region으로 나누는 이유와 효과는?"

### 3.2 키워드 1 — Region 구조 (2048 가이드)

```
Heap 전체를 2048개 region으로 (가이드):
   region 크기 = Heap / 2048 → 1, 2, 4, 8, 16, 32MB 중 자동 선택

[Eden][Eden][Surv][Old][Old][Free][Hum][Hum]
[Old][Free][Eden][Surv][Old][Free][...]
[Free][Old][Old][Eden][Surv][Old][...]
...

각 region이 type을 가짐:
   - Eden / Survivor (Young)
   - Old
   - Humongous
   - Free
```

### 3.3 키워드 2 — Region의 동적 역할 변경

```
GC 진행에 따라 같은 region이 역할 변경:

GC 1: region X = Eden
   → mutator allocation
GC 2: region X의 살아있는 객체 → 다른 region으로 evacuate
   → region X = Free
GC 3: region X = Old (다른 GC에서 promote 객체 수용)
GC 4: region X의 객체들 다 죽음
   → region X = Free
...

→ Young/Old의 물리적 분리 없음
→ 같은 메모리 공간이 시간 따라 다양하게 쓰임
→ 메모리 효율 ↑
```

### 3.4 키워드 3 — Humongous Object

```
Region 크기 = 4MB (예시)
새 객체 > 2MB (region의 50%)
   → Humongous로 분류
   → Old gen에서 연속된 region(s) 할당
   → Young GC 건너뜀, Mixed/Full GC에서만 회수

운영 함정:
   1. 큰 객체 빈번 → fragmentation
   2. 일찍 죽어도 Old GC 기다림 → 메모리 점유 ↑
   3. 한 Humongous가 region 일부만 사용 → 남는 공간 낭비
```

자세히는 [Chapter 02-01 Heap and TLAB](../02-runtime-data-areas/01-heap-and-tlab.md).

### 3.5 Remembered Set (Region별)

```
각 region의 RSet = "어느 region의 어디서 나를 가리키나" 목록.

Mixed GC에서 cross-region ref 추적의 핵심.

운영 함정:
   cross-region 참조 dense → RSet 비대화
   → Mixed GC 시간 ↑
```

자세히는 [Chapter 02-06 GC Bookkeeping](../02-runtime-data-areas/06-gc-bookkeeping-and-others.md).

---

## 4. 가지 ④: G1의 GC 종류 — Young / Mixed / Full

### 4.1 핵심 질문

> "G1은 어떤 종류의 GC를 가지고 있고, 각각 언제 발생하나요?"

### 4.2 키워드 1 — Young GC

```
트리거: Eden region들이 모두 가득
흐름:
   1. STW 시작
   2. Eden + Survivor의 살아있는 객체를 다른 region으로 evacuate
   3. age + 1, 또는 Old로 promote
   4. STW 끝

특징:
   - 빈도: 자주 (~수 초)
   - STW: ~수십 ms (MaxGCPauseMillis 목표 안에)
```

### 4.3 키워드 2 — Mixed GC (G1의 핵심)

```
트리거: Old 사용량 임계 도달 (-XX:InitiatingHeapOccupancyPercent=45)

흐름:
   1. Concurrent Marking 시작 (SATB, mutator와 동시)
   2. Marking 완료 후 Mixed GC 시작:
      - STW
      - Young region + 일부 Old region (garbage-rich) 같이 evacuate
      - STW 끝
   3. 수 회 Mixed GC로 충분한 Old 정리
   4. 정상 운영 재개

특징:
   - "Garbage First" — 쓰레기 많은 region부터 수집
   - 적은 작업으로 많은 메모리 회수
   - STW 예측 가능 (region 수 조정)
```

### 4.4 키워드 3 — Full GC (G1의 사고)

```
G1의 Full GC는 운영 사고 신호:
   - Mixed GC가 따라가지 못함
   - Allocation rate가 너무 빠름
   - Humongous 누적

흐름: Mark-Compact (STW, 매우 김)

→ G1에서 Full GC가 보이면 즉시 진단 필요
```

### 4.5 SATB (Snapshot-At-The-Beginning)

```
G1의 Concurrent Marking 정확성 보장:
   - Marking 시작 시점에 객체 그래프 "snapshot"
   - 그 후 mutator가 ref 변경해도 snapshot에서 살아있던 것은 살림
   - Pre-write barrier로 옛 ref를 SATB queue에 enqueue
   - Marker가 queue 처리

CMS의 Incremental Update와 다른 방식:
   IU: "변경된 ref를 추적해 추가로 mark"
   SATB: "변경 전 옛 ref도 살림 (snapshot)"
```

---

## 5. 가지 ⑤: Pause Prediction Model — G1의 영혼

### 5.1 핵심 질문

> "G1의 `-XX:MaxGCPauseMillis`가 어떻게 동작하나요?"

### 5.2 키워드 1 — 통계 기반 예측

```
G1이 매 GC마다 통계 수집:
   - Region별 evacuate 시간
   - RSet 스캔 시간
   - Roots scan 시간
   - Object copy throughput

다음 GC 결정:
   목표 = MaxGCPauseMillis (기본 200ms)
   - 통계 기반 예상 시간 계산
   - 목표 안에 들도록 수집할 region 수 조정
```

### 5.3 키워드 2 — Region 수 조정

```
[빠른 GC가 가능한 상황]
   Live ratio 낮음, RSet 작음
   → 더 많은 region 수집 (목표 시간 내에 가능)

[GC가 느린 상황]
   Live ratio 높음, RSet 큼
   → 적은 region만 수집 (목표 시간 초과 회피)
   → Old 누적 빨라짐 → Mixed GC 빈도 ↑
```

### 5.4 키워드 3 — Trade-off (목표 시간의 의미)

```
-XX:MaxGCPauseMillis 작게 (50):
   + Latency 좋음
   - Throughput ↓ (잦은 GC)
   - Heap을 효과적으로 못 씀

-XX:MaxGCPauseMillis 크게 (500):
   + Throughput ↑
   - Latency spike

권장: 200 (기본). 워크로드 측정 후 조정.
```

**중요**: MaxGCPauseMillis는 **목표지 보장이 아니다**. 워크로드에 따라 초과 가능.

### 5.5 G1 옵션 매트릭스

```
-XX:+UseG1GC                          # G1 활성 (기본, JDK 9+)
-XX:MaxGCPauseMillis=200              # 목표 STW
-XX:G1HeapRegionSize=32m              # region 크기 (자동, 수동 가능)
-XX:InitiatingHeapOccupancyPercent=45 # concurrent marking 시작 임계
-XX:G1MixedGCLiveThresholdPercent=85  # Mixed GC 대상 region의 live ratio 한계
-XX:G1HeapWastePercent=5              # 허용 낭비
-XX:G1ReservePercent=10               # Old 예약 공간 (Promotion Failure 회피)
```

99% 기본값. MaxGCPauseMillis만 워크로드별 조정.

### 5.6 HotSpot 내부 (참고)

**G1CollectedHeap** (`src/hotspot/share/gc/g1/g1CollectedHeap.cpp`):
```cpp
class G1CollectedHeap : public CollectedHeap {
    HeapRegionManager* _hrm;          // region 관리
    G1Policy*          _policy;        // pause prediction
    G1RemSet*          _g1_rem_set;    // Remembered Set
    G1ConcurrentMark*  _cm;            // concurrent marking
};
```

**G1Policy — Pause Prediction**:
```cpp
size_t compute_target_region_count() {
    double target_time = MaxGCPauseMillis;
    double per_region_cost = _predictions.avg_evacuation_time();
    return target_time / per_region_cost;
}
```

매 GC 후 통계 업데이트 → 다음 GC의 region 수 결정.

---

## 6. 면접 답변 워크플로우

### 6.1 질문 → 가지 매핑

| 면접 질문 | 진입 가지 | 인접 확장 |
|---|---|---|
| "CMS phase는?" | ① CMS 6 phase | 한계로 |
| "CMS가 왜 제거됐나?" | ② CMS 한계 | 4가지 |
| "G1의 region 설계 이점?" | ③ G1 region | Mixed GC |
| "Humongous object?" | ③ G1 region | 운영 함정 |
| "G1의 GC 종류?" | ④ G1 GC 종류 | Mixed GC 핵심 |
| "MaxGCPauseMillis 동작?" | ⑤ Pause Prediction | 통계 |
| "G1 Full GC가 보이면?" | ④ Full GC | 사고 진단 |

### 6.2 답변 템플릿

예: "G1의 region 설계가 어떤 이점을 주나요?"

> "G1은 Heap을 region (보통 2048개)으로 나누고 garbage-rich region부터 evacuate합니다 (← 루트).
> Region 설계의 이점은 가지 ③의 키워드 3개에 있습니다.
> 첫째, **fragmentation 해결**. region 단위 evacuate라 자연스럽게 compact.
> 둘째, **동적 역할 변경**. 같은 region이 Eden → Old → Free로 변하니 메모리 효율 ↑.
> 셋째, **Humongous 처리**. region 크기의 50% 이상 객체는 연속 region 할당.
> 더 큰 이점은 가지 ⑤에 — region 수 조정으로 **MaxGCPauseMillis 목표** 안에 STW 들어가게."

---

## 7. 꼬리질문 트리

### Q1 [가지 ②]. CMS가 왜 제거됐나요?

> 4가지 본질적 한계:
> 1. **Fragmentation** (Mark-Sweep만, compact 없음 → 큰 객체 할당 실패).
> 2. **Concurrent Mode Failure** (GC가 mutator 못 따라감 → 응급 Full GC).
> 3. **Floating Garbage** (concurrent mark 중 죽은 객체는 다음 cycle).
> 4. **CPU 영향 + 유지보수 부담**.
> JEP 363 (JDK 14)에서 완전 제거. G1이 대체.

**🪝 Q1-1: CMS의 Incremental Update와 G1의 SATB 차이는?**
> IU (CMS): 변경된 ref를 추적해 추가로 mark. SATB (G1): 변경 전 옛 ref도 살림 (snapshot). 둘 다 concurrent marking 정확성 보장 메커니즘.

### Q2 [가지 ③]. G1의 region 기반 설계의 이점은?

> 1. **Fragmentation 줄임** (region 단위 evacuate).
> 2. **STW 예측 가능** (region 수 조정 → MaxGCPauseMillis 목표).
> 3. **Mixed GC로 Full GC 회피** (garbage-rich Old region 점진적 정리).
> 4. **Humongous object 처리** (연속 region 할당).

### Q3 [가지 ⑤]. MaxGCPauseMillis는 어떻게 동작하나요?

> G1의 pause prediction model:
> - 매 GC 통계 수집 (region별 evacuation 시간, RSet scan 시간 등).
> - 다음 GC 시 목표 시간 안에 끝나도록 region 수 조정.
> - **보장이 아닌 목표** — 워크로드 따라 초과 가능.

**🪝 Q3-1: 50ms로 너무 작게 설정하면?**
> 잦은 GC + 적은 region 수집 → throughput ↓ + Old 누적 빨라짐 → Mixed GC 빈도 ↑. 권장 200ms.

### Q4 [가지 ④]. G1에서 Full GC가 발생하면?

> 운영 사고 신호. 원인: Mixed GC가 따라가지 못함, allocation rate 폭증, Humongous 누적.
> 즉시 진단:
> 1. GC log에서 Full GC cause 확인.
> 2. Heap dump로 Old gen 분석.
> 3. -XX:G1ReservePercent 늘리거나 ZGC 검토.

### Q5 (Killer) [가지 ③+⑤]. G1 사용 중 Mixed GC pause가 200ms → 800ms로 늘었습니다. 진단하세요.

> 1. **GC log 상세 분석**:
>    ```
>    -Xlog:gc+phases=debug
>    ```
>    어느 phase가 길어졌나? Scan RS / Update RS / Object Copy 중.
>
> 2. **RSet 추세**:
>    ```
>    -Xlog:gc+remset=info
>    ```
>    `fine->coarse transitions` 빈발 시 RSet 비대.
>
> 3. **원인 식별**:
>    - 큰 cache + cross-region ref 폭증 → RSet 비대.
>    - Humongous 누적.
>    - Heap 크기 증가 → region 수 증가.
>
> 4. **조치**:
>    - `-XX:G1HeapRegionSize=32m` (region 크기 ↑ → 수 ↓ → RSet 수 ↓).
>    - Cache 크기 제한 (cross-region ref 줄임).
>    - ZGC 검토 (cross-gen RSet이 더 효율, 100GB+ Heap).

---

## 8. 학습 체크리스트

- [ ] 0장 마인드맵을 1분 이내로 그릴 수 있다 (루트 + 5가지 + 키워드 3개)
- [ ] 가지 ①: CMS 6 phase를 외운다 (Init / Conc Mark / Preclean / Remark / Conc Sweep / Reset)
- [ ] 가지 ②: CMS 4가지 한계를 인용한다 (Frag / CMF / Float / CPU)
- [ ] 가지 ③: Region 2048 가이드와 동적 역할 변경을 그린다
- [ ] 가지 ③: Humongous 운영 함정 3가지를 말한다
- [ ] 가지 ④: Young / Mixed / Full GC 차이를 설명한다
- [ ] 가지 ④: SATB와 IU의 차이를 비교한다
- [ ] 가지 ⑤: Pause Prediction Model 동작을 설명한다
- [ ] 가지 ⑤: MaxGCPauseMillis trade-off (작게 vs 크게)를 말한다
- [ ] 7장 꼬리질문 5개에 답한다

---

## 다음 단계

- → [04. ZGC and Shenandoah](./04-zgc-and-shenandoah.md): Read Barrier + Concurrent Evacuation
- ← [02. Generational](./02-generational-and-serial-parallel.md)

## 참고

- **JEP 363 — Remove CMS**: https://openjdk.org/jeps/363
- **HotSpot `g1CollectedHeap.cpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/gc/g1/g1CollectedHeap.cpp
- **HotSpot `g1Policy.cpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/gc/g1/g1Policy.cpp
- **Oracle G1 Tuning**: https://docs.oracle.com/en/java/javase/21/gctuning/garbage-first-g1-garbage-collector1.html
