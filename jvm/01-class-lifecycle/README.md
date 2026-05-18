# 01. Class Lifecycle — .class 한 바이트부터 클래스 unload까지

> JVM의 모든 일은 **클래스를 로드해서, 검증하고, 연결하고, 초기화하고, 인스턴스 만들고, 결국 unload하는 것**의 반복이다.
> 이 사이클을 바이트 단위로 안다는 것은 JVM의 입구를 다 안다는 뜻이다.

---

## 학습 흐름

```
┌─────────────────────┐    ┌──────────────────────┐    ┌─────────────────────┐    ┌──────────────────────────┐
│ 01. ClassFile 포맷  │ →  │ 02. ClassLoader 계층  │ →  │ 03. Linking         │ →  │ 04. Initialization        │
│   .class 바이트 구조 │    │   부모 위임 + 변형    │    │   Verify · Prepare  │    │   <clinit> + 클래스 unload│
│                     │    │                      │    │   · Resolve         │    │                          │
└─────────────────────┘    └──────────────────────┘    └─────────────────────┘    └──────────────────────────┘
```

| # | 파일 | 핵심 질문 |
|---|---|---|
| 01 | [01-classfile-format.md](./01-classfile-format.md) | "CAFEBABE 다음에 무엇이 오나? 16바이트부터 마지막 attribute까지" |
| 02 | [02-classloader-hierarchy.md](./02-classloader-hierarchy.md) | "Bootstrap → Platform → App 위임은 어떻게 동작하고, Tomcat은 왜 그걸 깨나" |
| 03 | [03-linking.md](./03-linking.md) | "Verification은 어떻게 타입 안전성을 증명하고, Resolution은 언제 일어나나" |
| 04 | [04-initialization-and-unload.md](./04-initialization-and-unload.md) | "static 초기화 순서는? ClassLoader는 언제 unload되나" |

---

## ⛳ 가장 헷갈리는 한 가지 — 누가 무엇을 하는가 (책임 경계)

> **이 표는 4개 챕터 어디서든 다시 등장한다.** 한 번에 머리에 박아두자.
> 클래스 라이프사이클은 **세 주체(javac · ClassLoader · JVM 본체)**가 시간차로 협업한다.
> 락은 누가 잡는가? `<clinit>`은 누가 트리거하는가? 답이 항상 같다 → **JVM 본체**.

```
[컴파일 타임]                          [런타임 — Class 객체 생성 후]
                                ────────────────────────────────────────────
    javac          →   ClassLoader   →   JVM Linker      →   JVM Initializer
  ┌──────────┐       ┌──────────┐       ┌────────────┐      ┌──────────────┐
  │ .class에 │       │ bytecode │       │ Verify     │      │ Active Use 시 │
  │ <clinit>,│       │ → 메모리 │       │ Prepare    │      │ ★ init lock   │
  │ ConstantP│       │ Class 객체│       │ Resolve     │      │   12-step 발동│
  │ 합성·박음 │       │ 생성      │       │            │      │ <clinit> 실행 │
  └──────────┘       └──────────┘       └────────────┘      └──────────────┘
    01장              02장               03장                   04장
```

| 주체 | 시점 | 책임 | 락과의 관계 | 다루는 챕터 |
|---|---|---|---|---|
| **javac** (컴파일러) | 컴파일 타임 | `.class` 파일 생성, `<clinit>` 합성, ConstantPool 구성, ConstantValue 인라이닝 | 락에 관여 안 함 | **01** |
| **ClassLoader** | 런타임, 첫 참조 시 | `.class` 바이트 → 메모리에 `Class` 객체 생성 (**Loading만**) | init lock 안 잡음. `loadClass()` 자체는 자기 락(parallel CL)을 쓸 뿐 | **02** |
| **JVM Linker** | Loading 직후 (자동) | Verification(타입 안전성 증명) · Preparation(static 필드 default) · Resolution(심볼릭 → 직접, lazy) | init lock 안 잡음 | **03** |
| **JVM Initializer** | **Active Use 시점에만** | `<clinit>` 실행, JLS 12.4.2 **12-step lock 절차** 발동, ExceptionInInitializerError 처리 | ★ **여기서 per-Class `_init_lock` 잡음** | **04** |

### 🔑 자주 헷갈리는 3가지 — 한 번에 해소

1. **"ClassLoader가 클래스를 초기화한다"는 표현은 부정확**
   ClassLoader는 **Loading만** 한다. Linking/Initialization은 JVM 본체 책임.
   → "load"라는 단어가 광범위해서 생긴 오해. JVMS 기준으로 ClassLoader의 책임은 `.class` 바이트 → `Class` 객체까지.

2. **`ClassLoader.loadClass()`가 끝났다 ≠ `<clinit>`이 돌았다**
   클래스가 메모리에 올라와 있어도, **누가 Active Use(`new`, `getstatic`, `invokestatic`, `Class.forName(name, true)` 등)를 트리거하기 전까진 `<clinit>`은 절대 안 돈다.**
   → AppCDS, `Class.forName(name, false)`, `A.class` 같은 lazy 패턴이 가능한 근본 이유.

3. **JLS 12.4.2의 12-step 락은 ClassLoader가 잡는 락이 아니다**
   락은 **각 `Class` 객체에 박혀있는 per-Class 내부 모니터**(HotSpot: `InstanceKlass._init_lock`).
   JVM Initializer가 Active Use 시점에 그 락으로 12-step을 돌린다.
   → 전역 락 아님 → 서로 다른 클래스의 init은 병렬 가능.

---

## 5단 레이어 적용

모든 챕터에서 동일 템플릿:
1. 백지 그리기 가이드 (SVG 정답 그림과 비교)
2. 직관
3. 구조 (Mermaid + ASCII)
4. 내부 구현 (HotSpot C++ 발췌)
5. 역사
6. 꼬리질문 트리 (3단+)

## 사전 학습

- [00-overview](../00-overview/) 4편을 먼저 마스터하라.
- 특히 [03-jvm-architecture-bigpicture.md](../00-overview/03-jvm-architecture-bigpicture.md)의 ClassLoader Subsystem 박스를 머리에 박아둬야 한다.
