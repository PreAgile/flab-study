# flab — Deep Study Repository

JVM을 시작으로, "백지에서 창시자 수준까지" 깊이 학습하기 위한 자료 저장소.

## 현재 챕터

- **[jvm/](./jvm/)** — JVM 깊이 학습
  - JVM/JRE/JDK, 컴파일 흐름, 아키텍처, 역사 (00-overview)
  - Class Lifecycle — ClassFile, ClassLoader, Linking, Initialization (01-class-lifecycle)
  - Runtime Data Areas — Heap & TLAB 외 (02-runtime-data-areas, 진행 중)
  - 보강 챕터: 운영 시나리오, 실습 워크북, 트레이드오프 마스터표

## 학습 철학

각 토픽은 **7단 레이어**로 작성됨:

1. 백지 그리기 가이드 (Excalidraw)
2. 직관 (비유 + 정확한 정의)
3. 구조 (ASCII / Mermaid 다이어그램)
4. 내부 구현 (HotSpot C++ 소스 발췌)
5. 역사 (시대별 변화 + 이유)
6. 트레이드오프 (다른 대안과 비교)
7. 측정·진단 (JFR, jcmd, async-profiler, ...)

추가로 **꼬리질문 트리** (3단 이상 깊이) 로 면접 시뮬레이션.

## 사용법

각 챕터의 README가 그 챕터의 학습 흐름을 안내합니다.
SVG 다이어그램은 md 파일에 인라인 임베드되며, 편집은 `.excalidraw` 파일을 [excalidraw.com](https://excalidraw.com/)에서 열어서 가능합니다.

```bash
# Excalidraw 다이어그램 재생성
cd jvm
python3 _tools/gen_excalidraw.py
```
