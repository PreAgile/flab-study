# 04-05. Generational ZGC (JDK 21+) — Weak Hypothesis를 ZGC에

> 2018년부터 5년간 ZGC는 **single-generation** — 모든 객체를 한 영역에서 처리. Latency는 sub-ms로 압도적이었지만 throughput과 footprint가 G1보다 나빴다.
> 2023년 JDK 21에서 **Generational ZGC** 도입 — Young/Old 분리. **G1과 동등한 throughput + sub-ms STW** 양립.
> 시니어가 알아야 할 것: 차세대 default GC 가능성이 매우 큼. 큰 Heap + latency-critical 시스템은 즉시 검토.

---

## 🗺️ JVM 아키텍처 안에서 이 챕터의 위치

![generational zgc](./_excalidraw/05-generational-zgc.svg)

---

## 📍 학습 목표

1. **Single-gen ZGC의 한계** — throughput, footprint, allocation rate 모두 G1 대비 부족.
2. **Generational ZGC의 동기** — Weak Generational Hypothesis 활용.
3. **두 cycle**: Young GC (자주) + Old GC (가끔), 둘 다 concurrent.
4. **Promotion** 메커니즘 — Young 객체가 충분히 살면 Old로.
5. **Remembered Set** — Old → Young 참조 추적 (G1과 유사하지만 colored pointer 활용).
6. **`-XX:+ZGenerational`** 옵션 — JDK 21 preview, JDK 23+ stable.
7. 실측 성능 개선 — Oracle 발표 (Throughput ↑15%, Footprint ↓20%).
8. **마이그레이션 경로** — single-gen에서 generational로 옮기는 절차.
9. **장기 차세대 default 가능성** — G1 대체 후보.
10. 운영 시나리오: 큰 Heap + 고 throughput + latency 목표.

---

## 🎨 1단계: 백지 그리기 가이드

### Step 1: Single vs Generational 구조 비교

```
[Single-gen ZGC]
[Heap 전체] — 모든 객체 같이 mark/relocate

[Generational ZGC]
[Young region들][Old region들]
   ↓                ↓
Young GC 자주    Old GC 가끔
```

### Step 2: Young/Old 분리의 효과

```
일반 워크로드: 객체의 95%가 단명
   
[Single-gen]
GC 1번에 100% Heap scan → 모든 객체 처리
   
[Generational]
Young GC 20번: 5% Heap만 scan → 빠름 + 효율
Old GC 1번: 95% Heap의 살아있는 5% 객체만 scan
   = 같은 시간에 더 적은 작업
```

### 정답 그림

위의 [05-generational-zgc.svg](./_excalidraw/05-generational-zgc.svg) 참조.

---

## 🧠 2단계: 직관

### 핵심 비유

> **창고 청소 비유** (재방문):
> - **Single-gen ZGC** = 한 큰 창고를 통째 정리. 영업 안 멈추지만 작업 자체가 김.
> - **Generational ZGC** = 창고를 신규/장기 구역으로 분리. 신규 구역 자주 정리 (대부분 일찍 버려질 짐), 장기 구역 가끔. 영업 영향 동일하지만 효율 ↑.

### 정확한 정의 (비유와 분리)

| 용어 | 정의 |
|---|---|
| **Generational ZGC** | JDK 21+의 ZGC 변형. Young/Old 분리. `-XX:+UseZGC -XX:+ZGenerational`. |
| **Young GC (ZGC)** | Young region만 mark/relocate. 자주 발생. |
| **Old GC (ZGC)** | Old region 위주. 가끔. 단명 객체는 이미 Young GC에서 회수. |
| **Promotion (ZGC)** | Young에서 충분히 살아남은 객체를 Old로. age 기반 또는 region 단위. |
| **Remembered Set (ZGC)** | Old → Young 참조 추적. Colored pointer + region info 활용. G1의 RSet과 비슷하지만 더 효율. |
| **Multi-mapping memory** | ZGC의 기본 — generational에도 그대로 사용. |
| **Two-phase marking** | Young/Old 각자 mark cycle. 둘 다 concurrent. |

### 왜 Generational ZGC가 필요했나

```
[Single-gen ZGC의 본질적 한계]

매 GC cycle:
   - 전체 Heap mark (concurrent)
   - 전체 Heap relocation (필요한 region)
   - 모든 객체가 같은 정책

문제:
   - 단명 객체도 전체 cycle 비용 분담
   - Live ratio가 영역별 다른데 평균값으로 처리 → 비효율
   - Throughput 비용: 단명 객체 mark/check이 모든 cycle에 누적
   
실측:
   - Throughput: G1의 85%
   - Footprint: G1보다 20% 큼
   - Allocation rate 한계: ~1GB/s

→ Latency만 보면 ZGC 압도. 그러나 다른 면에서 G1 대비 trade-off.
```

### Generational의 효과

```
[Young GC만 자주]
   - Young 영역만 scan → 매우 빠름
   - 단명 객체 빠르게 회수
   - Old GC 빈도 ↓

[Old GC는 가끔]
   - 살아남은 객체 위주 (대부분 alive)
   - 회수 효율 낮지만 빈도 낮음

→ 두 cycle의 분리가 efficiency 큰 폭 개선
→ G1과 동등 throughput, ZGC 그대로의 latency
```

---

## 🔬 3단계: 구조

### Generational ZGC의 cycle

```
[Young Cycle (자주, 수 초)]
1. Young Pause Mark Start (STW, ~0.1ms)
2. Concurrent Mark Young (mutator 동시)
3. Young Pause Mark End (STW, ~0.1ms)
4. Concurrent Relocate Young
5. Promotion: 충분히 산 객체 → Old

[Old Cycle (가끔, 수 분)]
1. Old Pause Mark Start (STW)
2. Concurrent Mark Old (mutator + Young GC 동시)
3. Old Pause Mark End (STW)
4. Concurrent Relocate Old

[두 cycle 동시 진행 가능]
- Young GC와 Old GC가 concurrent하게 같이 동작
- 단, mark 시작/끝의 짧은 STW는 조정 필요
```

### Promotion 정책

```
Young 객체의 age tracking:
   - colored pointer에 age 비트 포함
   - 각 Young GC에서 age 증가
   - Tenuring threshold 도달 → Old로 promote

또는 Survival-based:
   - 같은 region이 N번 Young GC 살아남음 → 통째 Old region으로
```

### Remembered Set 활용

```
[Old → Young 참조 추적]
   Old gen 객체가 Young 객체 가리킴
   → 그 참조는 RSet에 기록
   → Young GC 시 RSet 참조해 reachability 계산

ZGC의 RSet은 G1보다 효율:
   - Colored pointer가 cross-generation 참조 표시
   - 별도 자료구조 작음
```

### 실측 성능 (Oracle 발표)

```
환경: SPECjbb2015 등 표준 벤치마크

Throughput:
   Single-gen ZGC: G1의 85%
   Generational ZGC: G1과 동등

Footprint:
   Single-gen ZGC: G1보다 20% 큼
   Generational ZGC: G1과 동등

Allocation rate:
   Single-gen ZGC: ~1GB/s
   Generational ZGC: ~수 GB/s

STW:
   둘 다 < 1ms (유지)
```

→ 사실상 **G1의 모든 장점 + ZGC의 latency**.

---

## 🧬 4단계: 내부 구현 — HotSpot

### Generational ZGC 진입

위치: `src/hotspot/share/gc/z/zGeneration.cpp` (JDK 21+)

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

### Promotion

```cpp
oop ZGenerationYoung::promote(oop obj) {
    if (obj->age() >= TenuringThreshold) {
        return _old_gen->allocate(obj->size());
    }
    return _young_gen->allocate(obj->size());
}
```

---

## 📜 5단계: 역사

| 연도 | 변화 |
|---|---|
| 2018 | JDK 11 — ZGC 실험 (single-gen) |
| 2019 | JDK 13 — ZGC uncommit memory 개선 |
| 2020 | JDK 15 — ZGC production-ready |
| 2021 | JDK 17 — ZGC 16TB Heap |
| 2023 | **JDK 21 — Generational ZGC** (JEP 439, preview) |
| 2024 | JDK 23 — Generational ZGC stable |
| 미래 | 차세대 default GC 가능성 |

### JEP 439의 동기

> "Single-gen ZGC가 latency는 압도적이지만 throughput/footprint trade-off로 일반 채택 못 함. Generational 도입으로 G1 대체 가능한 GC 만들기."

---

## ⚖️ 6단계: 트레이드오프

### 옵션 선택 (JDK 21+)

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

---

## 📊 7단계: 측정·진단

### Generational ZGC log

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
```

`Y:` = Young, `O:` = Old.

### 운영 시나리오: G1 → Generational ZGC

```
환경: 50GB Heap, 일반 web service, P99 latency 100ms 목표
현재: G1, P99 80ms 정상

검토:
1. JDK 21+ 사용 가능한가?
2. 메트릭 시스템이 RSS 기준인가? (pmap 함정 회피)
3. Read barrier 비용 감수 가능한가? (throughput 영향 ~5%)

마이그레이션:
1. Canary 1대 — G1 → Generational ZGC
2. 메트릭 비교: throughput, P99, footprint, GC time
3. 안정 후 확대
4. -XX:+UseZGC -XX:+ZGenerational
```

---

## ⚔️ 8단계: 꼬리질문 트리

### Q1. Generational ZGC가 single-gen 대비 무엇이 좋아졌나요?

> 1. **Throughput**: G1 대비 85% → 100% (G1 동등).
> 2. **Footprint**: G1 대비 +20% → 동등.
> 3. **Allocation rate**: 1GB/s → 수 GB/s.
> 4. **STW**: < 1ms 유지.
> 
> Weak Generational Hypothesis 활용 — 단명 객체를 Young 영역만 효율적으로 처리.

### Q2. Young/Old cycle이 어떻게 동시 진행하나요?

> 둘 다 concurrent. 짧은 STW phase만 조정 필요.
> Young GC가 자주 (수 초마다), Old GC가 가끔 (수 분마다).
> Old → Young 참조는 Remembered Set으로 추적 (colored pointer 활용).

### Q3. (Killer) JDK 21로 업그레이드 후 G1에서 Generational ZGC로 옮길지 결정하는 기준은?

> 1. **Latency 목표**: P99 < 10ms 필요면 ZGC 확실.
> 2. **Heap 크기**: 32GB+면 ZGC 이점.
> 3. **Throughput 영향**: ~5% 감소 감수 가능?
> 4. **운영 도구**: RSS 기준 메트릭? pmap 함정 처리?
> 5. **마이그레이션 비용**: GC log 형식 변경, 알람 재설정.
> 6. **JDK 23+ stable** 이후 본격 도입 권장.
> 
> Canary로 시작 → 메트릭 비교 → 단계적 확대.

---

## 🔗 다음 단계

- → [06. GC Tuning and Ops](./06-gc-tuning-and-ops.md)
- ← [04. ZGC and Shenandoah](./04-zgc-and-shenandoah.md)
