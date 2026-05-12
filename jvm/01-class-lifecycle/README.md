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
