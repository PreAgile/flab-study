# 04-02. Generational GC + Serial / Parallel — Java GC의 첫 30년

> 1996년 Serial GC부터 2017년 G1이 default가 되기 전까지, Java GC의 사실상 표준은 **Young/Old 분할 + Copying/Mark-Compact 조합**이었다.
> Serial은 single-thread, Parallel은 그 멀티코어 버전. CMS/G1/ZGC가 모두 이 위에 쌓아 올라간 기반이다.
> 시니어가 알아야 할 것: 최신 GC를 이해하려면 이 기반을 백지에서 그릴 수 있어야 한다. **"Young GC가 빠른 이유"와 "Full GC가 비싼 이유"** 모두 여기서 출발.

---

## 이 문서의 사용법

1. **0장 마인드맵을 먼저 외운다** — 루트 한 문장 + 4가지 가지 + 각 가지의 키워드 3개.
2. **1~4장을 순서대로 학습한다** — 각 장이 마인드맵의 한 가지에 대응.
3. **5장 면접 워크플로우로 검증** + **6장 꼬리질문으로 깊이 점검**.

---

## 0. 마인드맵 — 면접 종이에 그릴 그림

### 루트 한 문장 (anchor)

> **"Young은 Eden+Survivor 2개로 Copying하고, age가 차면 Old로 promote한다. Serial은 1996년의 single-thread, Parallel은 그 멀티코어 확장이다."**

### 4개 가지 — 순서를 외운다

```
                [ROOT: Young = Copying + Survivor toggle / Old = Mark-Compact]
                                       │
       ┌──────────────────┬──────────────────┬──────────────────┐
       │                  │                  │                  │
     ① Heap 분할      ② Young GC          ③ Old GC          ④ Serial vs Parallel
   (Eden/Survivor/Old) (Copying + age)    (Mark-Compact)    (single vs multi)
       │                  │                  │                  │
   ┌───┼───┐         ┌────┼────┐         ┌───┼───┐         ┌────┼────┐
  8:1:1   Young/Old   S0↔S1     Tenuring  Promotion  Full GC   1996   2002
  비율    분할        ping-pong  threshold Failure    트리거    JDK1.0 JDK1.4
  NewRatio Hypothesis            동적조정              -Xmn 등           batch 적합
```

### 가지별 핵심 키워드

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① Heap 분할** | Eden 80% / S 10% / S 10% | NewRatio 2 (Young 1/3) | Weak Generational Hypothesis |
| **② Young GC** | Copying (Eden+활성 S → 비활성 S) | Tenuring (age + 1) | Dynamic threshold 조정 |
| **③ Old GC** | Mark-Compact | Promotion Failure → Full GC | -Xmn / NewRatio 조정 |
| **④ Serial vs Parallel** | 1996 vs 2002 | single vs multi thread | 작은 Heap vs batch |

### 면접 답변 흐름

> 면접관 질문 → 루트 문장 → 가지 선택 → 키워드 3개 순서대로 → 인접 가지로 확장

---

## 1. 가지 ①: Heap 분할 — Eden/Survivor/Old의 비율과 이유

### 1.1 핵심 질문

> "Heap을 어떻게 분할하나요? Eden, Survivor 0, Survivor 1, Old의 역할과 비율은?"

### 1.2 키워드 1 — 4분할 그림

```
[Young: 33%]                        |  [Old: 67%]
[Eden 80%][S0 10%][S1 10%]          |  [Tenured]
   ↑                                    ↑
   신규 할당 (TLAB)                     장기 생존
```

기본값:
- `-XX:NewRatio=2` → Old:Young = 2:1 → Young은 전체의 1/3.
- `-XX:SurvivorRatio=8` → Eden:S0:S1 = 8:1:1 → Eden 80%, Survivor 각 10%.

### 1.3 키워드 2 — Weak Generational Hypothesis의 활용

```
일반 Java 앱의 객체 수명 분포:
   1세대 후 죽음: 80~90%
   2세대 후 죽음: 5~10%
   3세대 이상 살아남음: 5~10% → Old로 promote

→ Young GC가 95% 메모리를 통째 reclaim 가능
→ Old는 살아있는 객체 비율 높음 → Mark-Compact가 적합
```

자세히는 [01. GC Fundamentals의 가지 ③](./01-gc-fundamentals.md).

### 1.4 키워드 3 — 왜 Survivor가 2개 (S0, S1)인가

```
Copying 알고리즘은 두 영역이 필수:
   - 한 영역(source)에서 다른 영역(target)으로 복사
   - 다음 GC에서 source/target toggle

GC 1: Eden + S0(active) → S1
GC 2: Eden + S1(active) → S0
GC 3: Eden + S0(active) → S1
...

Eden은 항상 source. Survivor 둘이 ping-pong.
```

→ 만약 Survivor가 1개면 Copying의 source/target이 같은 곳이 되어 알고리즘 자체가 성립 안 함.

---

## 2. 가지 ②: Young GC — Copying + Tenuring

### 2.1 핵심 질문

> "Young GC는 어떻게 동작하고, 객체는 언제 Old로 promote되나요?"

### 2.2 키워드 1 — Young GC 흐름

```
1. STW 시작
2. GC Roots scan (모든 thread stack + static + JNI ...)
3. Card Table 스캔 → Old → Young 참조 추가
4. Reachable Young 객체를 inactive Survivor로 copy
   - age + 1
   - age > MaxTenuringThreshold → Old로 promote
   - Survivor 부족 → Old로 promote
5. Eden 통째 비움, 옛 active Survivor 통째 비움
   새 active Survivor = 방금 copy받은 곳
6. STW 끝
```

**비용**: live ratio에 비례. 살아있는 객체 적으면 매우 빠름 (~10~50ms).

### 2.3 키워드 2 — Tenuring (Old로 promote)

```
객체 헤더에 age 카운터 (4비트 = max 15)
매 Young GC 살아남으면 age + 1

Promote 조건:
   1. age > MaxTenuringThreshold (기본 15)
   2. Survivor 공간 부족 (강제 promote)
   3. Humongous object (G1) — 처음부터 Old로
```

### 2.4 키워드 3 — Dynamic Tenuring Threshold 조정

```
정적: age > MaxTenuringThreshold → promote

동적 (실제 JVM 동작):
   각 GC 후 Survivor 사용량 측정
   if (Survivor 차서 OK):
       MaxTenuringThreshold 유지 또는 ↑
   if (Survivor 거의 가득):
       MaxTenuringThreshold ↓ (더 빨리 promote)

→ JVM이 적절한 threshold를 자동으로 찾음
→ 운영자가 옵션 명시 거의 안 함
```

**시니어 관점**: `-XX:MaxTenuringThreshold` 수동 설정은 거의 효과 없음. JVM 자동 조정이 더 정확.

---

## 3. 가지 ③: Old GC — Mark-Compact + Promotion Failure

### 3.1 핵심 질문

> "Full GC는 언제 발생하고 왜 비싼가요?"

### 3.2 키워드 1 — Old GC (Full GC) 흐름

```
트리거:
   1. Old 사용량 임계 도달
   2. Promotion failure (Young GC가 Old로 못 옮김)
   3. Metaspace 압박
   4. System.gc() 명시 호출

흐름 (Mark-Compact):
   1. STW 시작
   2. 전체 Heap mark (Young + Old)
   3. Compact (살아있는 객체를 한쪽으로)
   4. 모든 참조 주소 갱신
   5. STW 끝

비용: Heap 크기에 비례 (수백 ms ~ 수 초)
```

### 3.3 키워드 2 — Promotion Failure (가장 흔한 사고)

```
Young GC 진행 중:
   살아남은 객체를 Old로 promote 시도
   → Old 공간 부족
   → Promotion Failure 발생
   → 강제로 Full GC 트리거
   → STW 매우 김

GC log:
   "GC--- [PSYoungGen: 32M->32M] [ParOldGen: 250M->255M] (Allocation Failure)"
   "Pause Full" 메시지

원인:
   - Cache 비대화 (Old gen에 누적)
   - Young이 너무 작음 (premature promotion)
   - Allocation rate 폭증
```

### 3.4 키워드 3 — Young 크기 조정 (가장 흔한 튜닝)

```
-Xmn 또는 -XX:NewRatio로 Young 비율 조정

Young이 너무 작으면:
   - Young GC 빈도 ↑
   - 객체가 Old로 빨리 promote (premature promotion)
   - Old 빠르게 가득 → Full GC 빈발

Young이 너무 크면:
   - Young GC 시간 ↑ (마지막 mark 시간)
   - Old 작아져서 큰 객체 못 받음

권장: 기본값에서 시작. 측정 후 조정.
```

---

## 4. 가지 ④: Serial vs Parallel — 1996 vs 2002의 차이

### 4.1 핵심 질문

> "Serial GC와 Parallel GC의 차이는? 언제 어느 걸 쓰나요?"

### 4.2 키워드 1 — Serial GC (1996, JDK 1.0)

```
모든 phase가 single-thread:
   - Mark: 1 thread
   - Copy: 1 thread
   - Compact: 1 thread

장점:
   - 단순
   - 메모리 footprint 작음 (GC thread 별도 없음)
   - Thread overhead 0

단점:
   - 멀티코어 활용 못 함

적합:
   - 작은 Heap (<512MB)
   - 단일 코어 환경
   - 개발/테스트
   - 컨테이너 매우 제한적 (1 CPU)

옵션: -XX:+UseSerialGC
```

### 4.3 키워드 2 — Parallel GC (2002, JDK 1.4)

```
Young GC: 멀티스레드 copy
   - n threads (기본 자동 = CPU 수)
   - 각 thread가 GC Roots 일부 + reachable 객체 일부 처리
   - 작업 분배: work-stealing

Old GC: 멀티스레드 Mark-Compact (Parallel Old, JDK 6+)
   - 같은 방식

장점:
   - 멀티코어 충분히 활용
   - Throughput 매우 높음

단점:
   - STW 그대로 (단지 짧아짐)
   - Latency 부적합

적합:
   - Throughput 최우선 (batch, analytics)
   - Latency 신경 안 씀
   - JDK 8까지 기본 GC (-server)

옵션: -XX:+UseParallelGC (Parallel Old 자동 포함)
```

### 4.4 키워드 3 — Default GC 변천 + 선택 가이드

| JDK 버전 | Default | 변경 이유 |
|---|---|---|
| JDK 1.0~1.3 | Serial | 멀티코어 보편화 전 |
| JDK 1.4~8 | Parallel | Throughput 우선 시대 |
| JDK 9+ | **G1** | Latency 시대 |

**선택 가이드**:

| 워크로드 | GC | 이유 |
|---|---|---|
| 작은 Heap (<512MB), 1 코어 | Serial | thread overhead 회피 |
| Batch (Spark, Hadoop) | Parallel | throughput 최대 |
| 일반 web service | G1 | latency 예측 가능 |
| Latency-critical | ZGC/Shenandoah | sub-ms STW |

→ Latency-critical은 다음 챕터부터.

### 4.5 옵션 매트릭스

```
-XX:NewRatio=2              # Old:Young = 2:1 (Young은 1/3)
-XX:SurvivorRatio=8         # Eden:S0:S1 = 8:1:1
-XX:MaxTenuringThreshold=15 # age 한계 (4비트 max)
-XX:ParallelGCThreads=N     # Parallel GC thread 수
-Xmn 256m                    # Young 절대 크기 지정 (NewRatio 무시)
```

99% 기본값으로 충분. 운영 변경 시 측정 필수.

### 4.6 HotSpot 내부 (참고)

**SerialHeap** (`src/hotspot/share/gc/serial/serialHeap.hpp`):
```cpp
class SerialHeap : public CollectedHeap {
    DefNewGeneration*  _young_gen;   // Eden + Survivor
    TenuredGeneration* _old_gen;      // Old

    void do_collection(...) {
        if (young_only_collection) {
            _young_gen->collect(...);    // Copying
        } else {
            _old_gen->collect(...);       // Mark-Compact
        }
    }
};
```

**Copy 알고리즘** (Cheney's algorithm):
```cpp
void DefNewGeneration::copy_to_survivor_space(oop obj) {
    HeapWord* new_addr = to_space->allocate(obj->size());
    if (new_addr == NULL) {
        new_addr = _old_gen->allocate(obj->size());  // Promotion 시도
        if (new_addr == NULL) handle_promotion_failure();  // → Full GC
    }
    Copy::aligned_disjoint_words(obj, new_addr, obj->size());
    obj->set_forwardee(new_addr);   // forwarding pointer
    new_addr->incr_age();
    if (new_addr->age() > MaxTenuringThreshold) promote_to_old(new_addr);
}
```

---

## 5. 면접 답변 워크플로우

### 5.1 질문 → 가지 매핑

| 면접 질문 | 진입 가지 | 인접 확장 |
|---|---|---|
| "Eden/Survivor/Old 비율은?" | ① Heap 분할 | Hypothesis로 |
| "Survivor가 왜 2개?" | ① Heap 분할 | Copying 알고리즘 |
| "Young GC가 빠른 이유?" | ② Young GC | live ratio 5% |
| "Tenuring threshold 동적 조정?" | ② Young GC | Survivor 측정 |
| "Promotion Failure 진단?" | ③ Old GC | Young 크기 조정 |
| "Serial vs Parallel?" | ④ Serial vs Parallel | 워크로드 매핑 |
| "왜 JDK 9에서 G1이 default가 됐나?" | ④ + 다음 챕터 | latency 시대 |

### 5.2 답변 템플릿

예: "Young GC가 Full GC보다 빠른 이유는?"

> "Young은 Eden + Survivor 2개로 Copying하고, age가 차면 Old로 promote합니다 (← 루트).
> Young GC가 빠른 근본 이유는 가지 ②와 ③의 비교에 있습니다.
> 첫째, **live ratio 차이**. Young의 살아있는 객체는 ~5%, Old는 ~80%+.
> 둘째, **알고리즘 적합성**. Copying은 살아있는 거만 복사하면 끝 → 5%만 복사하고 95% 통째 reclaim.
> 셋째, **Mark-Compact는 모든 객체 이동 + 참조 갱신**. Old의 80% 객체를 모두 옮겨야 함.
> Weak Generational Hypothesis (객체 80~98%가 일찍 죽음)가 이 분할의 근거입니다."

---

## 6. 꼬리질문 트리

### Q1 [가지 ①]. Eden과 Survivor의 비율이 8:1:1인 이유는?

> 신규 할당이 Eden에 집중되고 (TLAB도 Eden 위치), Weak Generational Hypothesis로 80~90% 객체가 첫 GC에서 죽음. 그래서 Eden을 크게 (80%) 잡고 Survivor를 작게 (각 10%) 둠. Survivor는 첫 GC 살아남은 5~10% 객체만 임시 보관하면 충분.

**🪝 Q1-1: NewRatio=2의 의미는?**
> Old:Young = 2:1 → Young은 전체 Heap의 1/3. 일반 워크로드 기준 적절한 비율. Heavy allocation 워크로드면 Young을 키우는 게 효율적 (-XX:NewRatio=1).

### Q2 [가지 ②]. Survivor 영역이 왜 2개인가?

> Copying 알고리즘이 source/target 두 영역 필수. Eden + active Survivor → inactive Survivor로 복사 후 toggle. Eden은 항상 source. S0/S1이 ping-pong.

**🪝 Q2-1: Survivor가 가득 차면?**
> 강제 promotion. age threshold 미달이어도 Old로 promote. Survivor 부족이 잦으면 Young 너무 작은 신호.

### Q3 [가지 ②]. Tenuring threshold 동적 조정이 무엇인가요?

> JVM이 매 GC 후 Survivor 사용량 측정해서 MaxTenuringThreshold 자동 조정.
> Survivor 가득 → threshold ↓ (빨리 promote).
> Survivor 여유 → threshold 유지.
> 운영자가 명시 설정 거의 안 함 — JVM 자동이 더 정확.

### Q4 [가지 ③]. Promotion Failure가 무엇이고 결과는?

> Young GC가 살아남은 객체를 Old로 옮기지 못함 (Old 공간 부족).
> 결과: Full GC 강제 트리거. STW 매우 김.
> 원인: cache 비대, Young 너무 작음, allocation rate 폭증.
> 해결: Heap 크기 ↑, Young 크기 조정 (-Xmn), cache LRU eviction.

### Q5 [가지 ④]. Serial과 Parallel을 어떻게 선택?

> Heap 크기 + CPU 수 + 워크로드:
> - <512MB + 1 코어 + 개발: Serial.
> - 1GB+ + 멀티코어 + batch: Parallel.
> - 일반 service + latency 중요: G1 (다음 챕터).
> Serial은 thread overhead 회피, Parallel은 throughput 최대화.

### Q6 (Killer) [가지 ③+④]. Parallel GC 사용 중 분당 Full GC 5회. 진단하세요.

> 1. **GC log 확인**:
>    - "Allocation Failure" → Old 가득 (Promotion Failure 의심).
>    - "Metadata GC Threshold" → Metaspace 압박.
>    - "System.gc()" → 명시 호출 (RMI, DirectMemory).
> 2. **Heap dump + MAT**:
>    - Old gen에 어떤 객체가 누적? Cache 누수? Listener?
> 3. **-XX:+PrintTenuringDistribution**:
>    - MaxTenuringThreshold가 자주 낮아지면 premature promotion.
> 4. **단기 조치**: Heap 크기 ↑ (container limit 내), -Xmn 또는 NewRatio 조정.
> 5. **장기 조치**: 누수 코드 수정, G1으로 마이그레이션 (예측 가능한 STW).

---

## 7. 학습 체크리스트

- [ ] 0장 마인드맵을 1분 이내로 그릴 수 있다 (루트 + 4가지 + 키워드 3개씩)
- [ ] 가지 ①: Eden/S0/S1/Old 비율 (8:1:1:33% / 33% / 67%)을 그린다
- [ ] 가지 ①: Survivor가 2개인 이유 (Copying source/target)를 설명한다
- [ ] 가지 ②: Young GC 흐름 6단계를 적는다
- [ ] 가지 ②: Tenuring threshold 동적 조정을 설명한다
- [ ] 가지 ③: Promotion Failure → Full GC 흐름을 그린다
- [ ] 가지 ③: Young 크기 조정 trade-off를 말한다
- [ ] 가지 ④: Serial vs Parallel을 워크로드별로 매핑한다
- [ ] 가지 ④: JDK 9에서 default가 G1으로 바뀐 이유를 설명한다
- [ ] 6장 꼬리질문 6개에 답한다

---

## 다음 단계

- → [03. CMS and G1](./03-cms-and-g1.md): Region 기반 진화
- ← [01. GC Fundamentals](./01-gc-fundamentals.md)

## 참고

- **HotSpot `serialHeap.hpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/gc/serial/serialHeap.hpp
- **HotSpot `defNewGeneration.cpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/gc/serial/defNewGeneration.cpp
- **Oracle GC Tuning Guide (JDK 21)**: https://docs.oracle.com/en/java/javase/21/gctuning/
