# 12. Tradeoff Master Table — Cross-chapter 종합 비교

> "왜 X 대신 Y?" — 모든 시니어 질문의 핵심.
> 본 챕터는 챕터 전체의 트레이드오프를 한 표로 종합.

---

## 📊 GC 7종 종합

| | Serial | Parallel | CMS (제거) | G1 | ZGC (single) | Shenandoah | Gen ZGC |
|---|---|---|---|---|---|---|---|
| JDK | 1.0+ | 1.4+ | 1.4~13 | 7+, 9 default | 11~ | 12~ | 21+ |
| Young algo | Copying | Parallel Copy | Parallel Copy | Region Evac | Concurrent | Concurrent | Concurrent |
| Old algo | Mark-Compact | Mark-Compact | Concurrent MS | Region Evac | Concurrent | Concurrent | Concurrent |
| STW pause | 수백 ms ~ 수초 | 수십 ~ 수백 ms | ~100 ms (CMF 시 김) | 10~200 ms (목표) | < 1 ms | ~10 ms | < 1 ms |
| Throughput | 보통 | 높음 | 보통 | 보통~높음 | 85% (G1 대비) | 85% | 100% (G1 동등) |
| Heap 한계 | <512MB | ~수십 GB | ~수십 GB | ~수백 GB | 16TB | ~수백 GB | 16TB |
| 메모리 효율 | 좋음 | 좋음 | △ (frag) | 좋음 | 부담 (~20%) | 좋음 | 좋음 |
| 적합 | 작은 Heap, 단일코어 | Batch, throughput | (제거) | 일반 서비스 | 큰 Heap latency | Latency portable | 신규 default |
| 옵션 | -XX:+UseSerialGC | -XX:+UseParallelGC | (제거) | -XX:+UseG1GC | -XX:+UseZGC | -XX:+UseShenandoahGC | -XX:+UseZGC -XX:+ZGenerational |

## 📊 컴파일 모델 5종

| | Interpreter only | C1 only | C2 only | Tiered (기본) | AOT/Native Image |
|---|---|---|---|---|---|
| Startup | 즉시 | 빠름 | 매우 느림 | 빠름 | 가장 빠름 (수십 ms) |
| Peak throughput | 매우 낮음 | 보통 | 최고 | 최고 | 약간 낮음 (~90%) |
| Code Cache | 0 | 작음 | 보통 | 큼 | 0 (binary에 포함) |
| 옵션 | -Xint | -XX:TieredStopAtLevel=1 | -XX:-TieredCompilation | (기본) | native-image |
| 적합 | 디버깅, 재현 | 컨테이너 작음 | Batch | 일반 | Serverless, CLI |

## 📊 Threading 모델 3종

| | Platform Thread (1:1) | Virtual Thread (M:N) | Async (CompletableFuture) |
|---|---|---|---|
| Memory | 1MB/thread (OS stack) | ~수 KB (Heap chunk) | 0 (continuation 없음) |
| 최대 수 | ~수천 | 수십만~수백만 | 무제한 |
| 생성 비용 | ~수 ms | ~수 us | ~수 us |
| Synchronous 코드 | ✅ | ✅ | ❌ (async only) |
| Blocking I/O | ❌ (thread 점유) | ✅ (freeze) | ❌ |
| CPU-bound | ✅ | △ (carrier 점유) | △ |
| synchronized | ✅ | ❌ pinning (JDK 21~23) | ✅ |
| 디버깅 | 정상 | 정상 (stack trace) | 어려움 (callback hell) |

## 📊 JVM 구현 비교

| | HotSpot | OpenJ9 | GraalVM | Native Image |
|---|---|---|---|---|
| Author | Oracle | IBM Eclipse | Oracle | Oracle |
| Compiler | C2 (C++) | TR (C++) | Graal (Java) | AOT Graal |
| Footprint | 보통 | 작음 (~30% ↓) | 보통 | 작음 (~70% ↓) |
| Startup | 보통 | 빠름 | 보통 | 가장 빠름 |
| Peak throughput | 최고 | 약간 ↓ | 일부 ↑ | 약간 ↓ |
| 운영 maturity | 매우 성숙 | 성숙 | 성숙 중 | 성숙 중 |
| 적합 | 일반 | 메모리 제약 | Polyglot, 큰 throughput | Serverless |

## 📊 동기화 메커니즘 비교

| | synchronized | ReentrantLock | volatile | CAS (AtomicXxx) |
|---|---|---|---|---|
| 메커니즘 | JVM Mark Word | Java AQS | Memory barrier | lock cmpxchg |
| 비용 (no contention) | ~수십 cycles | ~수십 cycles | ~30 cycles (write) | ~10 cycles |
| 비용 (contention) | OS park/unpark | OS park/unpark | N/A | retry |
| 정확성 | 모든 mutate | 모든 mutate | visibility만 | atomicity 보장 |
| Try-lock | ❌ | ✅ | N/A | ✅ |
| Interruption | ❌ | ✅ | N/A | N/A |
| Condition | wait/notify | 여러 Condition | N/A | N/A |
| VT pinning | ❌ | ✅ | ✅ | ✅ |

## 📊 옵션 매트릭스 — Container 환경

```
2 CPU, 4GB limit:
  -Xms2g -Xmx2g
  -XX:MaxMetaspaceSize=256m
  -XX:MaxDirectMemorySize=512m
  -XX:ReservedCodeCacheSize=128m
  -XX:+UseG1GC -XX:MaxGCPauseMillis=200

4 CPU, 8GB limit:
  -Xms4g -Xmx4g
  -XX:MaxMetaspaceSize=512m
  -XX:MaxDirectMemorySize=1g
  -XX:ReservedCodeCacheSize=256m
  -XX:+UseG1GC -XX:MaxGCPauseMillis=100

16 CPU, 64GB limit:
  -Xms32g -Xmx32g
  -XX:MaxMetaspaceSize=1g
  -XX:MaxDirectMemorySize=4g
  -XX:ReservedCodeCacheSize=512m
  -XX:+UseZGC -XX:+ZGenerational (JDK 21+)
  또는 -XX:+UseG1GC
```

## ⚔️ 결정 트리

```
1. Startup이 가장 중요?
   YES → Native Image (GraalVM) 또는 Serial/C1-only
   NO → 2번

2. P99 latency 목표 < 10ms?
   YES → ZGC 또는 Generational ZGC (JDK 21+)
   NO → 3번

3. Throughput 최우선 (batch)?
   YES → Parallel GC + -XX:-TieredCompilation
   NO → 4번

4. 일반 서비스 (대부분):
   → G1 (기본) + Tiered Compilation (기본)

5. I/O bound 동시성 ↑↑?
   → Virtual Thread (JDK 21+)
```

---

## 🔗 다음 단계

- → [09. Mock Interviews](../09-mock-interviews/)
- 모든 챕터 cross-reference의 한 점.
