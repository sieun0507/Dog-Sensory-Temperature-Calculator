// 1. 라이브러리 포함
#include "DHT.h"

// 2. 핀 번호 설정
#define DHTPIN 2       // DHT 센서 데이터 핀
#define DHTTYPE DHT22  // DHT22 센서 사용 (만약 DHT11이면 DHT11로 변경)

#define GREEN_LED_PIN 4
#define YELLOW_LED_PIN 5
#define RED_LED_PIN 6
#define BUZZER_PIN 7

// 3. 객체 생성
DHT dht(DHTPIN, DHTTYPE);

// 4. 데이터 전송 시간 관리를 위한 변수
unsigned long previousMillis = 0;
const long interval = 2000; // 2초 간격

void setup() {
  // 시리얼 통신 시작 (파이썬과 통신 속도 맞추기)
  Serial.begin(9600);
  
  // DHT 센서 초기화
  dht.begin();
  
  // LED와 부저 핀을 출력 모드로 설정
  pinMode(GREEN_LED_PIN, OUTPUT);
  pinMode(YELLOW_LED_PIN, OUTPUT);
  pinMode(RED_LED_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  
  // 시작 시 모든 LED와 부저 끄기
  setAlarm('O'); // Off
}

void loop() {
  // --- 작업 1: 2초마다 센서 데이터 PC로 전송 ---
  unsigned long currentMillis = millis();
  if (currentMillis - previousMillis >= interval) {
    previousMillis = currentMillis;

    float h = dht.readHumidity();
    float t = dht.readTemperature();

    // 센서 읽기 실패 시 재시도
    if (isnan(h) || isnan(t)) {
      Serial.println("Failed to read from DHT sensor!");
      return;
    }

    // "온도,습도" 형식으로 PC에 데이터 전송
    Serial.print(t);
    Serial.print(",");
    Serial.println(h);
  }

  // --- 작업 2: PC로부터 제어 신호 수신 ---
  if (Serial.available() > 0) {
    char command = Serial.read(); // PC가 보낸 신호(한 글자) 읽기
    setAlarm(command); // 읽은 신호에 따라 LED/부저 제어
  }
}

// LED와 부저를 제어하는 함수
void setAlarm(char command) {
  // 일단 모든 LED와 부저를 끈다.
  digitalWrite(GREEN_LED_PIN, LOW);
  digitalWrite(YELLOW_LED_PIN, LOW);
  digitalWrite(RED_LED_PIN, LOW);
  noTone(BUZZER_PIN);

  // 받은 신호에 따라 해당 부품만 켠다.
  if (command == 'S') { // Safe
    digitalWrite(GREEN_LED_PIN, HIGH);
  } else if (command == 'C') { // Caution
    digitalWrite(YELLOW_LED_PIN, HIGH);
  } else if (command == 'D') { // Danger
    digitalWrite(RED_LED_PIN, HIGH);
    tone(BUZZER_PIN, 1000); // 1000Hz 주파수로 부저 울림
  }
}