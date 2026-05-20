# 04-05. Generational ZGC (JDK 21+) — Weak Hypothesis를 ZGC에

> 2018년부터 5년간 ZGC는 **single-generation** — 모든 객체를 한 영역에서. Latency는 sub-ms로 압도적이었지만 throughput과 footprint가 G1보다 나빴다.
> 2023년 JDK 21에서 **Generational ZGC** 도입 — Young/Old 분리. **G1과 동등한 throughput + sub-ms STW** 양립.
> 시니어가 알아야 할 것: 차세대 default GC 가능성이 매우 큼. 큰 Heap + latency-critical 시스템은 즉시 검토.

---

## 이 문서의 사용법

1. **0장 마인드맵을 먼저 외운다**.
2. **1~4장을 순서대로 학습한다**.
3. **5장 면접 워크플로우** + **6장 꼬리질문**.

---

## 0. 마인드맵 — 면접 종이에 그릴 그림

### 루트 한 문장 (anchor)

> **"Single-gen ZGC는 throughput과 footprint가 G1보다 나빴다. Generational ZGC는 Young/Old를 분리해 두 cycle을 concurrent로 돌리며 G1 동등 throughput + sub-ms STW를 동시에 달성한다."**

### 4개 가지 — 순서를 외운다

```
              [ROOT: Single-gen 한계 → Young/Old 분리로 G1 동등 + sub-ms]
                                  │
       ┌──────────────────┬──────────────────┬──────────────────┐
       │                  │                  │                  │
     ① Single-gen      ② Young/Old        ③ 두 cycle 동시    ④ 실측 성능 + 마이그
       한계               분리 효과          진행                + 미래
       │                  │                  │                  │
   ┌───┼───┐         ┌────┼────┐         ┌───┼───┐         ┌────┼────┐
  Throughput Footprint Hypothesis Promotion  Young (자주)  Old (가끔) Throughput  마이그레이션
  G1의85%   G1+20%   활용        + RSet      mark/relocate            +15%       절차
                                               동시                              차세대default
```

### 가지별 핵심 키워드

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① Single-gen 한계** | Throughput G1의 85% | Footprint +20% | Allocation rate ~1GB/s |
| **② Young/Old 분리** | Weak Hypothesis 재활용 | Promotion (age + colored ptr) | RSet (colored pointer 효율) |
| **③ 두 cycle 동시** | Young cycle 자주 | Old cycle 가끔 | 둘 다 concurrent + 짧은 STW |
| **④ 성능 + 미래** | Throughput G1 동등 | 차세대 default 가능성 | 마이그레이션 절차 |

### 면접 답변 흐름

> 면접관 질문 → 루트 문장 → 해당 가지 → 키워드 3개 → 인접 가지로 확장

---

## 1. 가지 ①: Single-gen ZGC의 한계 — 왜 Generational이 필요했나

### 1.1 핵심 질문

> "Single-gen ZGC가 latency는 압도적이었는데, 왜 G1을 대체 못 했나요?"

### 1.2 키워드 1 — Throughput G1의 85%

```
Single-gen ZGC의 본질적 한계:
   매 GC cycle:
      - 전체 Heap mark (concurrent이지만 작업량 큼)
      - 전체 Heap relocation (필요한 region)
      - 모든 객체가 같은 정책

문제:
   - 단명 객체도 전체 cycle 비용 분담
   - Live ratio가 영역별 다른데 평균값으로 처리 → 비효율
   - Throughput 비용: 단명 객체 mark/check이 모든 cycle에 누적

실측: G1 대비 throughput 85%
```

### 1.3 키워드 2 — Footprint +20%

```
Single-gen ZGC의 메모리 부담:
   - Multi-mapping (가상 3배, RSS는 1배지만)
   - 모든 객체의 colored pointer 처리
   - 더 많은 reserved memory

실측: G1 대비 footprint +20%
```

### 1.4 키워드 3 — Allocation rate 한계 ~1GB/s

```
Single-gen ZGC가 처리 가능한 allocation rate:
   ~1GB/s 정도가 한계
   
이유:
   - 전체 Heap 단위로 작업
   - 단명 객체가 폭증해도 한 cycle에서 모두 처리해야

워크로드:
   - 일반 web service: OK
   - High-throughput batch: 부족
   - Allocation rate 폭증하는 microservice: 한계 도달
```

→ Latency 가치만 보면 ZGC. 그러나 throughput/footprint trade-off로 일반 채택 못 함.

---

## 2. 가지 ②: Young/Old 분리 — Weak Hypothesis를 ZGC에

### 2.1 핵심 질문

> "Generational ZGC는 어떻게 Young/Old를 분리하나요?"

### 2.2 키워드 1 — Weak Generational Hypothesis 재활용

```
가지 ① [01. GC Fundamentals](./01-gc-fundamentals.md)에서 본 Hypothesis:
   "대부분 객체는 일찍 죽는다" (80~98%)

[Single-gen ZGC]
GC 1번에 100% Heap scan → 모든 객체 처리

[Generational ZGC]
Young GC 20번: 단명 객체만 scan → 빠름 + 효율
Old GC 1번: 살아남은 5% 객체만 scan
= 같은 시간에 더 적은 작업
```

### 2.3 키워드 2 — Promotion 메커니즘

```
Young 객체의 age tracking:
   - Colored pointer에 age 비트 포함
   - 각 Young GC에서 age 증가
   - Tenuring threshold 도달 → Old로 promote

또는 Survival-based:
   - 같은 region이 N번 Young GC 살아남음
   - → 통째로 Old region으로 변환 (region 단위 promotion)

HotSpot 의사 코드:
   oop ZGenerationYoung::promote(oop obj) {
       if (obj->age() >= TenuringThreshold) {
           return _old_gen->allocate(obj->size());
       }
       return _young_gen->allocate(obj->size());
   }
```

### 2.4 키워드 3 — Remembered Set (Old → Young 참조)

```
[Old → Young 참조 추적]
   Old gen 객체가 Young 객체 가리킴
   → 그 참조는 RSet에 기록
   → Young GC 시 RSet 참조해 reachability 계산

ZGC의 RSet은 G1보다 효율:
   - Colored pointer가 cross-generation 참조 표시
   - 별도 자료구조 작음
   - LRB와 통합 → barrier 비용 분담
```

→ G1의 region별 RSet과 비슷한 역할, ZGC는 colored pointer 덕에 더 효율.

---

## 3. 가지 ③: 두 cycle 동시 진행 — Young + Old Concurrent

### 3.1 핵심 질문

> "Young GC와 Old GC가 어떻게 동시에 진행하나요?"

### 3.2 키워드 1 — Young Cycle (자주, 수 초)

```
1. Young Pause Mark Start (STW, ~0.1ms)
2. Concurrent Mark Young (mutator 동시)
3. Young Pause Mark End (STW, ~0.1ms)
4. Concurrent Relocate Young
5. Promotion: 충분히 산 객체 → Old

특징:
   - Young region만 처리
   - 빠름 (전체 Heap의 5~20%만)
   - 단명 객체 빠르게 회수
```

### 3.3 키워드 2 — Old Cycle (가끔, 수 분)

```
1. Old Pause Mark Start (STW)
2. Concurrent Mark Old (mutator + Young GC 동시)
3. Old Pause Mark End (STW)
4. Concurrent Relocate Old

특징:
   - 살아남은 객체 위주 (대부분 alive)
   - 회수 효율 낮지만 빈도 낮음
   - Young GC와 동시 진행 가능
```

### 3.4 키워드 3 — 두 cycle 조정

```
Young GC와 Old GC가 concurrent하게 같이 동작:
   - Young cycle은 자주 진행 중
   - Old cycle은 그 위에서 background로

조정 필요한 시점:
   - Mark 시작/끝의 짧은 STW (두 cycle이 같은 STW에서)
   - Promotion 시점 (Young → Old)
   - Cross-cycle 참조 추적

결과:
   둘 다 sub-ms STW 유지
   throughput G1 동등
```

### 3.5 GC log 형식

```bash
java -XX:+UseZGC -XX:+ZGenerational -Xlog:gc* -jar app.jar
```

출력:
```
[gc] GC(0) Minor Collection (Allocation Rate)   ← Young GC
[gc] GC(1) Major Collection (Proactive)         ← Old GC
[gc,phases] GC(0) Y: Pause Mark Start 0.123ms
[gc,phases] GC(0) Y: Concurrent Mark 30ms
[gc,phases] GC(0) Y: Pause Mark End 0.234ms
[gc,phases] GC(0) Y: Concurrent Relocate 10ms
[gc,phases] GC(1) O: Pause Mark Start 0.345ms
...
```

`Y:` = Young, `O:` = Old.

---

## 4. 가지 ④: 실측 성능 + 마이그레이션 + 미래

### 4.1 핵심 질문

> "Generational ZGC의 실측 성능과 G1 대비 차이는? 언제 마이그레이션해야 하나?"

### 4.2 키워드 1 — 실측 성능 (Oracle 발표)

```
환경: SPECjbb2015 등 표준 벤치마크

Throughput:
   Single-gen ZGC: G1의 85%
   Generational ZGC: G1과 동등 ★

Footprint:
   Single-gen ZGC: G1보다 20% 큼
   Generational ZGC: G1과 동등 ★

Allocation rate:
   Single-gen ZGC: ~1GB/s
   Generational ZGC: ~수 GB/s

STW:
   둘 다 < 1ms (유지)
```

→ **사실상 G1의 모든 장점 + ZGC의 latency**.

### 4.3 키워드 2 — 마이그레이션 절차

```
환경: 50GB Heap, 일반 web service, P99 latency 100ms 목표
현재: G1, P99 80ms 정상

검토:
1. JDK 21+ 사용 가능한가?
2. 메트릭 시스템이 RSS 기준인가? (pmap 함정 회피)
3. Read barrier 비용 감수 가능한가? (throughput 영향 ~5%)

마이그레이션 단계:
1. Canary 1대 — G1 → Generational ZGC
   -XX:+UseZGC -XX:+ZGenerational
2. 메트릭 비교 24시간: throughput, P99, footprint, GC time, RSS
3. 안정 후 25% pod로 확대
4. 50%, 100% 확대
5. 알람 재설정:
   - GC time % 기준 변경 (ZGC는 매우 작음)
   - RSS 기준 (가상 메모리 알람 끄기)
   - STW pause 기준 < 5ms로
```

### 4.4 키워드 3 — 차세대 default 가능성

```
JDK 진화 시나리오 (예측):
   JDK 21 (LTS): G1 default, Generational ZGC preview
   JDK 23: Generational ZGC stable
   JDK 25+ (LTS, 2025): Generational ZGC default 가능성?

이유:
   - G1과 throughput 동등
   - latency 압도적 (sub-ms vs 50~200ms)
   - footprint 동등
   - 큰 Heap (TB) 지원

미해결:
   - pmap 함정 (모니터링 도구 학습 필요)
   - 일부 OS 호환성
```

### 4.5 GC 선택 가이드 (JDK 21+)

```
일반 서비스, ~수십 GB Heap:
   기본 G1 또는 Generational ZGC

Latency-critical, ~수십 GB:
   Generational ZGC (sub-ms STW)

큰 Heap (100GB+):
   Generational ZGC (G1보다 우수)

가장 큰 Heap (TB):
   Generational ZGC 거의 필수

옛 JDK 11~17:
   G1 (안정) 또는 ZGC single-gen (latency만)
```

### 4.6 HotSpot 내부 (참고)

**Generational ZGC 진입** (`src/hotspot/share/gc/z/zGeneration.cpp`, JDK 21+):
```cpp
class ZGeneration : public CHeapObj<mtGC> {
public:
    virtual void mark_start();
    virtual void mark_concurrent();
    virtual void mark_end();
    virtual void relocate();
};

class ZGenerationYoung : public ZGeneration { ... };
class ZGenerationOld   : public ZGeneration { ... };
```

각 generation이 자기 cycle 수행. ZHeap이 둘을 조정.

---

## 5. 면접 답변 워크플로우

### 5.1 질문 → 가지 매핑

| 면접 질문 | 진입 가지 | 인접 확장 |
|---|---|---|
| "Single-gen ZGC 한계는?" | ① Single-gen 한계 | throughput/footprint |
| "Generational의 동기?" | ② Young/Old 분리 | Hypothesis |
| "Young/Old cycle 동시 진행?" | ③ 두 cycle | STW 조정 |
| "G1 vs Gen ZGC 성능 비교?" | ④ 실측 성능 | 마이그레이션 |
| "차세대 default 가능?" | ④ 미래 | JDK 진화 |
| "마이그레이션 단계?" | ④ 마이그 절차 | canary |

### 5.2 답변 템플릿

예: "Generational ZGC가 Single-gen 대비 무엇이 좋아졌나요?"

> "Single-gen ZGC는 throughput과 footprint가 G1보다 나빴는데, Generational ZGC가 Young/Old 분리로 G1 동등 + sub-ms STW를 동시에 달성했습니다 (← 루트).
> 가지 ①의 한계가 가지 ②의 분리로 해결됩니다.
> 첫째, **Throughput**: G1 대비 85% → 100% (G1 동등).
> 둘째, **Footprint**: G1 대비 +20% → 동등.
> 셋째, **Allocation rate**: 1GB/s → 수 GB/s.
> 넷째, **STW**: < 1ms 유지.
> Weak Generational Hypothesis (단명 객체 95%)를 ZGC에 도입한 효과 — Young 영역만 효율적으로 처리하니 같은 메모리 회수량에 GC 비용 1/5~1/10."

---

## 6. 꼬리질문 트리

### Q1 [가지 ②]. Generational ZGC가 single-gen 대비 무엇이 좋아졌나요?

> 1. **Throughput**: G1 대비 85% → 100% (G1 동등).
> 2. **Footprint**: G1 대비 +20% → 동등.
> 3. **Allocation rate**: 1GB/s → 수 GB/s.
> 4. **STW**: < 1ms 유지.
>
> Weak Generational Hypothesis 활용 — 단명 객체를 Young 영역만 효율적으로 처리.

### Q2 [가지 ③]. Young/Old cycle이 어떻게 동시 진행하나요?

> 둘 다 concurrent. 짧은 STW phase만 조정 필요.
> Young GC가 자주 (수 초마다), Old GC가 가끔 (수 분마다).
> Old → Young 참조는 Remembered Set으로 추적 (colored pointer 활용).

**🪝 Q2-1: 두 cycle이 같은 STW를 공유하나?**
> Pause Mark Start/End 시점이 겹칠 수 있음. 그 때 둘 다 같은 STW에서 진행. 그래서 STW가 약간 길어질 수 있지만 여전히 < 1ms.

### Q3 [가지 ②]. Promotion 메커니즘은?

> Colored pointer에 age 비트 포함. 매 Young GC에서 age 증가. Tenuring threshold 도달 → Old로 promote.
> Region 단위 promotion도 가능 — 같은 region이 N번 살아남으면 통째로 Old region으로 변환.

### Q4 [가지 ④]. (Killer) JDK 21 업그레이드 후 G1에서 Generational ZGC로 옮길지 결정하는 기준은?

> 1. **Latency 목표**: P99 < 10ms 필요면 ZGC 확실.
> 2. **Heap 크기**: 32GB+면 ZGC 이점.
> 3. **Throughput 영향**: ~5% 감소 감수 가능?
> 4. **운영 도구**: RSS 기준 메트릭? pmap 함정 처리?
> 5. **마이그레이션 비용**: GC log 형식 변경, 알람 재설정.
> 6. **JDK 23+ stable** 이후 본격 도입 권장.
>
> Canary로 시작 → 메트릭 비교 → 단계적 확대.

### Q5 [가지 ④]. Generational ZGC가 차세대 default GC가 될까요?

> 가능성 높음. 이유:
> - G1과 throughput 동등 (Single-gen 시절 약점 해결).
> - Latency 압도적 (sub-ms vs G1의 50~200ms).
> - Footprint 동등.
> - 큰 Heap (TB) 지원 (G1은 ~수십 GB 적합).
>
> JDK 23+에서 stable화 진행 중. JDK 25 LTS (2025)에서 default 변경 가능성.
> 미해결: pmap 함정, 일부 OS 호환.

---

## 7. 학습 체크리스트

- [ ] 0장 마인드맵을 1분 이내로 그릴 수 있다
- [ ] 가지 ①: Single-gen ZGC의 3가지 한계 (throughput 85%, footprint +20%, alloc 1GB/s)를 인용한다
- [ ] 가지 ②: Weak Generational Hypothesis가 ZGC에 도입된 효과를 설명한다
- [ ] 가지 ②: Promotion 메커니즘 (age + colored pointer)을 그린다
- [ ] 가지 ③: Young/Old 두 cycle의 동시 진행을 그린다
- [ ] 가지 ③: GC log 형식 (`Y:`, `O:`)을 인식한다
- [ ] 가지 ④: Generational ZGC의 실측 성능 (G1 동등 + sub-ms)을 인용한다
- [ ] 가지 ④: 마이그레이션 단계 (canary → 25% → 50% → 100%)를 말한다
- [ ] 가지 ④: 차세대 default 가능성과 미해결 과제를 설명한다
- [ ] 6장 꼬리질문 5개에 답한다

---

## 다음 단계

- → [06. GC Tuning and Ops](./06-gc-tuning-and-ops.md): 운영 종합
- ← [04. ZGC and Shenandoah](./04-zgc-and-shenandoah.md)

## 참고

- **JEP 439 — Generational ZGC**: https://openjdk.org/jeps/439
- **HotSpot `zGeneration.cpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/gc/z/zGeneration.cpp
- **Oracle Generational ZGC blog (2023)**: https://inside.java/2023/11/28/gen-zgc-explainer/
- **Per Liden Generational ZGC talk**: JavaOne 2023+
