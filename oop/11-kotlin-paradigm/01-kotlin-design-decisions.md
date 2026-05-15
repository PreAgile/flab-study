# 11-01. Kotlin 설계 결정 — Java의 무엇을 의식적으로 뒤집었나

> "Kotlin = Java + syntax sugar"는 틀린 시각.
> JetBrains가 의식적으로 뒤집은 7가지 결정.

## 📍 7가지 설계 결정

### ① Nullable Type System

```kotlin
val a: String = "hello"       // Non-null
val b: String? = null         // Nullable

b.length    // 컴파일 에러
b?.length   // safe call
b!!.length  // not-null assertion (throw if null)
```

Java의 답: Optional. 그러나 명시적 박싱 비용.
Kotlin: **타입 시스템에 직접 명시**. 컴파일 시 검증.

### ② val/var 명시

```kotlin
val x = 10        // immutable
var y = 20        // mutable
```

Java의 답: `final` 키워드. 그러나 not default.
Kotlin: **immutable이 default 권장 패턴**.

### ③ Primary Constructor

```kotlin
class Point(val x: Int, val y: Int)
// = Java의 class + 생성자 + getter 자동
```

DTO/Record 패턴 표준.

### ④ Extension Function

```kotlin
fun String.upperFirst(): String =
    if (isEmpty()) this
    else this[0].uppercase() + substring(1)

"hello".upperFirst()  // "Hello"
```

기존 클래스에 메서드 추가 (실제로는 static method + syntactic sugar).

### ⑤ Data Class (Record before Record)

```kotlin
data class Order(val id: Long, val status: String)
// → equals, hashCode, toString, copy 자동
```

### ⑥ Coroutine (vs Thread)

```kotlin
suspend fun fetchData(): Data {
    val a = async { fetchA() }
    val b = async { fetchB() }
    return Data(a.await(), b.await())
}
```

Java의 답: CompletableFuture (callback-ish) → Virtual Thread (JDK 21+).
Kotlin: 처음부터 **structured concurrency** + 컴파일러가 CPS 변환.

### ⑦ Sealed (before Java)

```kotlin
sealed class Shape
class Circle(val r: Double) : Shape()
class Square(val side: Double) : Shape()

// Pattern matching
when (shape) {
    is Circle -> println(shape.r)
    is Square -> println(shape.side)
    // exhaustive — 빠지면 컴파일 에러
}
```

Java 17보다 6년 일찍 도입.

## 📊 Java vs Kotlin

| | Java 21 | Kotlin 1.9 |
|---|---|---|
| Null 안전 | Optional | Type system |
| Immutability | final | val/var (default 권장) |
| Boilerplate | Record | data class |
| 함수 표현력 | Lambda | First-class function |
| Pattern matching | switch | when |
| Async | Virtual Thread | Coroutine |
| Extension | static method | 1st class |

## ⚔️ 꼬리질문

### Q. Kotlin이 Java를 대체할까요?

> 부분적으로 Android에서 그렇다 (Google 공식 권장).
> 서버 side에서는 공존.
> Spring/JVM ecosystem이 Java 중심.
> Kotlin은 표현력 우위, Java는 ecosystem + LTS 안정성 우위.

### Q. Kotlin Coroutine vs Java Virtual Thread?

> 둘 다 lightweight concurrency.
> - **Coroutine**: 컴파일러 CPS 변환. structured concurrency 강제.
> - **Virtual Thread**: JVM 레벨. 기존 Java 코드 그대로.
> 
> Kotlin 코드는 Coroutine 자연.
> Java + Spring 코드는 Virtual Thread가 더 친화.

## 🔗 다음

- → [12. Spring & Framework](../12-spring-and-framework/)
