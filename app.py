import streamlit as st
import requests
import datetime
import serial
import time

# --- 아두이노 통신을 위한 설정 ---
# ❗️❗️❗️ 자신의 아두이노 포트에 맞게 수정해야 합니다! (예: 'COM3', '/dev/tty.usbmodem...')
ARDUINO_PORT = 'COM5' 

# ==============================================================================
# 섹션 1: 핵심 계산 및 API 연동 함수들
# ==============================================================================
def get_coords_from_nominatim(address):
    url = f"https://nominatim.openstreetmap.org/search?q={address}&format=json"; headers = {"User-Agent": "MyDogWeatherApp/1.0"}
    try:
        r = requests.get(url, headers=headers, timeout=10).json(); return r[0]['lat'], r[0]['lon'] if r else (None, None)
    except: return None, None
def get_weather(lat, lon, api_key):
    url = f"http://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={api_key}&units=metric&lang=kr"
    try:
        r = requests.get(url, timeout=10).json()
        if r.get("cod") == 200: return {"temp": r['main']['temp'], "humidity": r['main']['humidity'], "wind": r['wind']['speed'], "desc": r['weather'][0]['description']}
    except: return None
    return None
def calculate_human_temp(temp_c, humidity, wind_ms):
    if temp_c > 10:
        if temp_c < 27 or humidity < 40: return temp_c
        temp_f = temp_c * 1.8 + 32
        hi_f = -42.379 + 2.04901523*temp_f + 10.14333127*humidity - .22475541*temp_f*humidity - .00683783*(temp_f**2) - .05481717*(humidity**2) + .00122874*(temp_f**2)*humidity + .00085282*temp_f*(humidity**2) - .00000199*(temp_f**2)*(humidity**2)
        return round((hi_f - 32) / 1.8, 1)
    else:
        wind_kmh = wind_ms * 3.6
        if wind_kmh < 4.8: return temp_c
        wc = 13.12 + 0.6215*temp_c - 11.37*(wind_kmh**.16) + 0.3965*temp_c*(wind_kmh**.16)
        return round(wc, 1)
def get_dog_risk_final(temp, h, w, p):
    br, ar, fr = 0, [], 0
    if temp > 10:
        if 20<=temp<=25 and h>60: br=1
        elif 26<=temp<=31: br=2 if h>30 else 1
        elif 32<=temp<=37: br=3 if h>30 else 2
        elif temp>=38: br=3
        war=br
        if w>=1.4:
            if temp>=38: war+=(2 if w>4.0 else 1); ar.append(f"뜨거운 바람(+{2 if w>4.0 else 1})")
            else: war-=(2 if w>4.0 else 1); ar.append(f"시원한 바람(-{2 if w>4.0 else 1})")
        fr=war
        if p['coat']=='장모종/이중모': fr+=1; ar.append("더위에 약한 털(+1)")
        if p['breed']=='단두종': fr+=1; ar.append("단두종(+1)")
    else:
        s=p['size']
        if 1>=temp>-3 and s=='소형견': br=1
        elif -4>=temp>-8:
            if s=='소형견': br=2
            elif s=='중형견': br=1
        elif temp<=-9:
            if s=='소형견': br=3
            elif s=='중형견': br=2
            elif s=='대형견': br=1
        war=br
        if w>=1.4: war+=(2 if w>4.0 else 1); ar.append(f"차가운 바람(+{2 if w>4.0 else 1})")
        fr=war
        if p['coat']=='단모종': fr+=1; ar.append("추위에 약한 털(+1)")
        elif p['coat']=='장모종/이중모': fr-=2; ar.append("추위에 강한 털(-2)")
    a,s=p['age'],p['size']
    risk_age=(a<1) or (s=='소형견' and a>=10) or (s=='중형견' and a>=8) or (s=='대형견' and a>=7)
    if risk_age: fr+=1; ar.append("성장기/노령견(+1)")
    if p['body']=='비만 체형' and temp>10: fr+=1; ar.append("비만 체형(+1)")
    elif p['body']=='마른 편' and temp<=10: fr+=1; ar.append("마른 편(+1)")
    risk_levels = ["✅ 안전", "⚠️ 주의", "🚨 위험", "🆘 매우 위험"]
    final_risk_index = max(0, min(fr, 3))
    return risk_levels[final_risk_index], final_risk_index, ar
def get_arduino_data(ser):
    try:
        line = ser.readline().decode('utf-8').strip(); return float(line.split(',')[0]), float(line.split(',')[1]) if line else (None, None)
    except: return None, None
def send_command_to_arduino(ser, command):
    try: ser.write(command.encode())
    except: pass

# ==============================================================================
# 섹션 2: Streamlit UI 및 메인 로직
# ==============================================================================

st.set_page_config(layout="wide", page_title="🐾 반려견 날씨 알리미")

# --- 사이드바 UI ---
with st.sidebar:
    st.title("🐾 반려견 날씨 알리미")
    st.info("실시간 날씨를 분석하여 사람과 강아지의 산책 위험도를 알려줍니다.")
    if 'dogs' not in st.session_state: st.session_state.dogs = []
    st.header("⚙️ 기본 설정"); address = st.text_input("📍 위치 설정", "서울시청"); owm_api_key = st.text_input("🔑 OpenWeatherMap API 키", type="password")
    st.header("🐕 우리 강아지 프로필")
    for i, dog in enumerate(st.session_state.dogs):
        with st.expander(f"🐶 {dog['name']}", expanded=False):
            with st.form(key=f"edit_dog_{i}"):
                st.subheader(f"'{dog['name']}' 정보 수정"); edited_name = st.text_input("이름", value=dog['name']); edited_size = st.selectbox("크기",["소형견","중형견","대형견"], index=["소형견","중형견","대형견"].index(dog['size'])); edited_age = st.slider("나이",0,20,value=dog['age']); edited_coat = st.radio("털 종류",["단모종","장모종/이중모"], index=["단모종","장모종/이중모"].index(dog['coat']),key=f"coat_{i}"); edited_breed = st.radio("견종 특성",["일반견","단두종"], index=["일반견","단두종"].index(dog['breed']),key=f"breed_{i}"); edited_body = st.select_slider("체형", ["마른 편","보통 체형","비만 체형"], value=dog['body'])
                c1,c2=st.columns(2)
                if c1.form_submit_button("저장"): st.session_state.dogs[i]={'name':edited_name,'size':edited_size,'age':edited_age,'coat':edited_coat,'breed':edited_breed,'body':edited_body}; st.rerun()
                if c2.form_submit_button("삭제"): st.session_state.dogs.pop(i); st.rerun()
    with st.form("new_dog_form", clear_on_submit=True):
        st.subheader("➕ 새 강아지 추가"); new_name = st.text_input("이름"); new_size = st.selectbox("크기",["소형견","중형견","대형견"]); new_age = st.slider("나이",0,20,5); new_coat = st.radio("털 종류",["단모종","장모종/이중모"]); new_breed = st.radio("견종 특성",["일반견","단두종"]); new_body = st.select_slider("체형",["마른 편","보통 체형","비만 체형"])
        if st.form_submit_button("추가"):
            if new_name: st.session_state.dogs.append({'name':new_name,'size':new_size,'age':new_age,'coat':new_coat,'breed':new_breed,'body':new_body}); st.rerun()
            else: st.warning("이름을 입력해주세요.")

# --- 메인 화면 ---
st.header(f"📈 '{address}' 날씨 분석")

# 분석 결과를 표시할 공간을 미리 만듭니다.
result_placeholder = st.empty()

# 자동 새로고침 체크박스
auto_refresh = st.checkbox("🔄 1분마다 자동 새로고침")

# 분석 로직을 함수로 분리
def perform_analysis():
    ser = None
    try:
        with st.spinner("아두이노와 연결하고 데이터를 분석하는 중입니다..."):
            ser = serial.Serial(ARDUINO_PORT, 9600, timeout=2); time.sleep(2); ser.reset_input_buffer()
            indoor_temp, indoor_humidity = get_arduino_data(ser)
            lat, lon = get_coords_from_nominatim(address)
            outdoor_weather = get_weather(lat, lon, owm_api_key) if lat and lon else None
        
        if indoor_temp is not None and outdoor_weather:
            with result_placeholder.container(): # 지정된 공간에 결과를 그립니다.
                st.success("데이터 분석 완료!")
                indoor_data = {"temp": indoor_temp, "humidity": indoor_humidity, "wind": 0.0}
                outdoor_data = outdoor_weather
                
                # ... (이하 모든 계산 및 결과 표시 로직) ...
                highest_risk_level, riskiest_dog_name, highest_indoor_risk_index = "✅ 안전", "", 0
                if st.session_state.dogs:
                    outdoor_risks = [ (get_dog_risk_final(outdoor_data['temp'], outdoor_data['humidity'], outdoor_data['wind'], dog)[0], dog['name']) for dog in st.session_state.dogs ]
                    indoor_risks_indices = [ get_dog_risk_final(indoor_data['temp'], indoor_data['humidity'], indoor_data['wind'], dog)[1] for dog in st.session_state.dogs]
                    risk_order = {"🆘 매우 위험": 3, "🚨 위험": 2, "⚠️ 주의": 1, "✅ 안전": 0}
                    if outdoor_risks: highest_risk_level, riskiest_dog_name = max(outdoor_risks, key=lambda item: risk_order.get(item[0], 0))
                    if indoor_risks_indices: highest_indoor_risk_index = max(indoor_risks_indices)
                
                if highest_risk_level in ["🆘 매우 위험", "🚨 위험"]: st.error(f"### 🚨 산책 위험! \n`{riskiest_dog_name}`에게 특히 위험한 날씨입니다.")
                elif highest_risk_level == "⚠️ 주의": st.warning(f"### ⚠️ 산책 주의! \n`{riskiest_dog_name}`에게는 조금 힘든 날씨일 수 있습니다.")
                else: st.success(f"### ✅ 산책하기 좋은 날씨예요!")
                st.markdown("---")

                st.subheader("🧑 사람 체감온도"); col1, col2 = st.columns(2)
                human_indoor = calculate_human_temp(indoor_data['temp'], indoor_data['humidity'], indoor_data['wind'])
                human_outdoor = calculate_human_temp(outdoor_data['temp'], outdoor_data['humidity'], outdoor_data['wind'])
                col1.metric("🧊 실내", f"{human_indoor}°C", f"실제: {indoor_data['temp']}°C"); col2.metric("🌤️ 실외", f"{human_outdoor}°C", f"실제: {outdoor_data['temp']}°C ({outdoor_data['desc']})")

                st.subheader("🐕 우리 강아지별 위험도")
                if not st.session_state.dogs: st.info("사이드바에서 강아지를 추가하여 맞춤 위험도를 확인하세요.")
                else:
                    for dog in st.session_state.dogs:
                        with st.expander(f"**🐶 {dog['name']} - 상세 결과 보기**"):
                            risk_indoor, _, reasons_indoor = get_dog_risk_final(indoor_data['temp'], indoor_data['humidity'], indoor_data['wind'], dog)
                            risk_outdoor, _, reasons_outdoor = get_dog_risk_final(outdoor_data['temp'], outdoor_data['humidity'], outdoor_data['wind'], dog)
                            d_col1, d_col2 = st.columns(2)
                            with d_col1: st.metric("🧊 실내 위험도", risk_indoor); st.caption("계산 과정: " + (", ".join(reasons_indoor) if reasons_indoor else "기본 위험도"))
                            with d_col2: st.metric("🌤️ 실외 위험도", risk_outdoor); st.caption("계산 과정: " + (", ".join(reasons_outdoor) if reasons_outdoor else "기본 위험도"))
                
                command_map = ['S', 'C', 'D', 'V']
                command_to_send = command_map[highest_indoor_risk_index]
                send_command_to_arduino(ser, command_to_send)
                st.caption(f"아두이노에 '{command_to_send}' 제어 신호를 전송했습니다.")
        else:
            result_placeholder.error("아두이노 또는 API로부터 데이터를 가져오는 데 실패했습니다.")
    except serial.SerialException as e: st.error(f"아두이노 연결 실패: {e}")
    except Exception as e: st.error(f"분석 중 오류 발생: {e}")
    finally:
        if ser and ser.is_open: ser.close()

# --- 메인 제어 로직 ---
if st.button("수동 분석 실행"):
    if not owm_api_key:
        st.warning("사이드바에서 OpenWeatherMap API 키를 먼저 입력해주세요.")
    else:
        perform_analysis()

if auto_refresh:
    # 자동 새로고침이 켜져있을 때만 루프 실행
    perform_analysis()
    time.sleep(60) # 60초 대기
    st.rerun()