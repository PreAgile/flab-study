# 12. Tradeoff Master Table — cross-chapter 종합 비교

> 각 챕터 안에서도 트레이드오프를 다뤘지만,
> **한눈에 비교**할 수 있는 종합 표는 별개의 가치.
> 면접에서 "왜 X 대신 Y인가" 질문에 즉답하려면 이 표가 머리에 박혀 있어야 한다.

---

## 📍 학습 목표

이 챕터를 끝내면 다음 비교를 표를 안 보고 그릴 수 있다:
1. GC 7종 (Serial/Parallel/CMS/G1/ZGC/Shenandoah/Epsilon)의 트레이드오프
2. JVM 구현 5종 (HotSpot/OpenJ9/GraalVM/Zing/Avian)의 차이
3. AOT vs JIT vs Tiered Compilation
4. Threading 모델 3종 (Platform / Virtual / Reactive)
5. 메모리 영역 종류별 GC 정책
6. ClassLoader 모델별 격리 vs 성능
7. Memory Barriers 종류별 비용

---

## 비교 표 카탈로그 (작성 예정)

### 1. GC 종합 비교

| 속성 | Serial | Parallel | CMS | G1 | ZGC | Shenandoah | Epsilon |
|---|---|---|---|---|---|---|---|
| **도입 JDK** | 1.0 | 1.4 | 1.4 (제거 14) | 7 (default 9) | 11 (prod 15) | 12 (Red Hat) | 11 |
| **알고리즘** | mark-sweep-compact | parallel mark-sweep-compact | mark-sweep (Old만 concurrent) | region-based, mostly concurrent | colored pointers, fully concurrent | Brooks/LRB, fully concurrent | no-op |
| **세대 구분** | Y/O | Y/O | Y/O | Region 기반 (sof Y/O) | 21까지 single-gen, 21+ generational | Single-gen | N/A |
| **STW** | 길다 | 길다 | Old 짧음, Young 길음 | 예측가능 (목표) | < 1ms | < 1ms | 0 (수집 안함) |
| **Throughput** | 낮음 | ★★★★★ | ★★★ | ★★★★ | ★★★★ | ★★★★ | ★★★★★ |
| **Latency** | ★ | ★ | ★★★ | ★★★★ | ★★★★★ | ★★★★★ | ★★★★★ |
| **Heap 크기** | 작음 (~수백MB) | 중간 (~수십GB) | ~수십GB | ~수백GB | 8MB ~ 16TB | ~수백GB | 임의 |
| **메모리 오버헤드** | 작음 | 작음 | 중간 | 중간 | 큼 (~10%) | 큼 (~10%) | 0 |
| **유즈케이스** | 임베디드/CLI | 배치/Throughput | (deprecated) | 일반 서버 | 초저지연 + 큰 heap | 초저지연 + 큰 heap | benchmark, OOM 측정 |
| **활성화** | `-XX:+UseSerialGC` | `-XX:+UseParallelGC` | (제거됨) | `-XX:+UseG1GC` | `-XX:+UseZGC` | `-XX:+UseShenandoahGC` | `-XX:+UseEpsilonGC` |

### 2. JVM 구현 비교

| 속성 | HotSpot | OpenJ9 | GraalVM | Zing | Avian |
|---|---|---|---|---|---|
| **개발사** | Oracle/OpenJDK | IBM/Eclipse | Oracle Labs | Azul | 개인 |
| **JIT 언어** | C++ | C/C++ | **Java** | C++/LLVM | C++ |
| **AOT** | (JEP 295 제거) | shared cache | **Native Image** | Falcon (LLVM) | 부분 |
| **GC 종류** | G1/ZGC/Shenandoah | Balanced/Gencon | G1/ZGC | C4 (pauseless) | Mark-sweep |
| **메모리 footprint** | 큼 | 작음 | 작음 (Native Image) | 큼 | 매우 작음 |
| **Startup** | 보통 | 빠름 (shared cache) | 매우 빠름 (Native) | 보통 | 빠름 |
| **GC pause** | ~1ms (ZGC) | ~수십 ms | ~1ms (ZGC) | < 10ms (C4) | 길다 |
| **유즈케이스** | 표준 | Cloud, low footprint | Serverless, CLI | Trading | 임베디드 |

### 3. AOT vs JIT vs Tiered

| 속성 | AOT (Native Image) | JIT (C2 only) | Tiered (C1+C2) |
|---|---|---|---|
| **Startup** | < 100ms | 수~수십초 | 수초 |
| **Peak performance** | ★★★ | ★★★★★ | ★★★★★ |
| **메모리** | ★★★★★ (작음) | ★ (큼) | ★★ |
| **동적 기능** | 제한적 (closed-world) | 모두 가능 | 모두 가능 |
| **Reflection** | 별도 metadata 필요 | 완전 지원 | 완전 지원 |
| **유즈케이스** | FaaS, CLI, 콜드스타트 | 단일 워크로드 서버 | 일반 서버 (default) |

### 4. Threading 모델

| 속성 | Platform Thread | Virtual Thread (Loom) | Reactive |
|---|---|---|---|
| **1:1 OS thread** | 예 | 아니오 (M:N) | 아니오 |
| **Stack size** | 1MB | 가변 (Heap의 chunk) | 없음 (callback) |
| **Max concurrency** | ~수천 | 100만+ | 100만+ |
| **Blocking 모델** | OK | OK (자동 unmount) | 금지 (callback hell) |
| **코드 가독성** | ★★★★★ | ★★★★★ | ★★ |
| **디버깅** | ★★★★ | ★★★★ | ★★ |
| **CPU 효율** | ★★ | ★★★★ | ★★★★★ |
| **사용 시기** | 적은 동시성 + CPU 집중 | 많은 동시성 + I/O | 진짜 reactive 시나리오 |

### 5. Memory Barriers (CPU 아키텍처별)

| Barrier | 의미 | x86 (강한 모델) | ARM (약한 모델) |
|---|---|---|---|
| **LoadLoad** | 앞 load가 뒤 load보다 먼저 보이게 | (자동) | `DMB ISHLD` |
| **StoreStore** | 앞 store가 뒤 store보다 먼저 보이게 | (자동) | `DMB ISHST` |
| **LoadStore** | 앞 load 후 뒤 store | (자동) | `DMB ISH` |
| **StoreLoad** | 앞 store 후 뒤 load | `MFENCE` 또는 `lock add` | `DMB ISH` |

> volatile write는 모든 4가지 barrier. x86은 사실상 `lock add` 하나로 처리 가능.

### 6. ClassLoader 모델

| 모델 | 위임 방향 | 격리 | 메모리 |
|---|---|---|---|
| **표준 (Java)** | 부모 → 자기 | 약함 | 효율적 |
| **Tomcat WebappCL** | 자기 → 부모 (반전) | 강함 (앱별) | 중복 가능 |
| **OSGi BundleCL** | DAG (그래프) | 매우 강함 | 효율적 (의존성 명시) |
| **JPMS Module** | 모듈 그래프 | 강함 (모듈별 export) | 효율적 |

---

## 작성 진행 상황

⏳ 각 표를 상세 분석 + 트레이드오프 explained로 채울 예정.
이 챕터는 모든 본 챕터 (00~08) 학습 후 종합 정리용.
