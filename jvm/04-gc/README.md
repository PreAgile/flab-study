# 04. Garbage Collection — Serial부터 ZGC까지

> JVM의 가장 시각화되는 운영 지표가 GC pause다. P99 latency, 메모리 footprint, throughput 모두 GC와 직결.
> 1996년 Serial GC부터 2023년 Generational ZGC까지 30년의 진화를 따라가면 **각 알고리즘이 어떤 운영 사고를 해결하려 만들어졌는지** 보인다. 이게 시니어가 GC를 "외운" 수준과 "다룰 줄 아는" 수준을 가르는 경계.

---

## 🗺️ JVM 아키텍처 안에서 이 챕터의 위치

```
[Chapter 02 Runtime Data Areas] — Heap 구조 + Card Table + RSet (전제)
        │
        ▼
[★ 본 챕터: GC ★]
   - Serial / Parallel / CMS / G1 / ZGC / Shenandoah / Generational ZGC
   - SATB vs Incremental Update
   - Brooks Pointer vs Load Reference Barrier
   - Colored Pointer + Multi-mapping Memory
        │
        ▼
[Chapter 05 Threading] — Safepoint 메커니즘
[Chapter 10 Ops Scenarios] — Full GC 빈발, P99 spike 등
```

---

## 📚 Sub-chapter 목록

| # | 파일 | 핵심 질문 | 상태 |
|---|---|---|---|
| 01 | [01-gc-fundamentals.md](./01-gc-fundamentals.md) | Reachability, GC Roots, Mark-Sweep-Compact 기본 | ✅ |
| 02 | [02-generational-and-serial-parallel.md](./02-generational-and-serial-parallel.md) | Weak Generational Hypothesis, Serial, Parallel | ✅ |
| 03 | [03-cms-and-g1.md](./03-cms-and-g1.md) | CMS의 한계 → G1의 region 기반 + Remembered Set | ✅ |
| 04 | [04-zgc-and-shenandoah.md](./04-zgc-and-shenandoah.md) | Colored Pointer, Load Reference Barrier, Multi-mapping | ✅ |
| 05 | [05-generational-zgc.md](./05-generational-zgc.md) | JDK 21+ Generational ZGC — Weak Hypothesis를 ZGC에 | ✅ |
| 06 | [06-gc-tuning-and-ops.md](./06-gc-tuning-and-ops.md) | GC 선택 + 옵션 튜닝 + 운영 시나리오 | ✅ |

---

## 📏 작성 표준 룰

[`../../AGENTS.md`](../../AGENTS.md)의 5룰 적용.

---

## 🏢 시니어가 이 챕터에서 얻어야 할 능력

1. **GC 7종 선택 기준** — 워크로드 + Heap 크기 + latency 목표 + JDK 버전 매트릭스로 답할 수 있다.
2. **P99 spike의 GC 원인** 진단 — 어느 phase가 길었는지 GC log + JFR로 식별.
3. **Full GC 빈발 원인** — premature promotion / humongous allocation / Metaspace 압박.
4. **컨테이너 환경 GC 튜닝** — cgroup 인식, Heap 크기 결정.
5. **ZGC/Shenandoah 도입 판단** — 트레이드오프 + production case studies.
