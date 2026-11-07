# 소설 표지 시각 스타일 라이브러리
플랫폼과 장르에 따라 키워드를 골라 Step 3의 프롬프트 템플릿에 넣습니다. 디자인 지시는 영어로 작성하고 제목과 필명은 작가의 원문을 유지합니다.

---

## 플랫폼 스타일

| 플랫폼 | 화면 특징 | 키워드 문자열 |
|:-----|:---------|:---------|
| 판체(番茄) | 높은 채도와 대비. 인물이 화면의 60% 이상을 차지하고 얼굴이 선명함. 얼굴 중심 구도와 화려한 배경, 제목은 금색·빨강·흰색 굵은 글꼴에 빛 효과 적용 | `vibrant saturated colors, eye-catching bold design, character portrait dominating frame, mass-market novel cover style, high contrast` |
| 치뎬(起点) | 섬세하고 사실적인 삽화, 차분한 색감. 인물과 배경이 균형을 이루고 깊이감 있는 영화적 화면. 제목은 전통 붓글씨 해서체 계열 | `polished refined illustration, detailed cinematic composition, epic atmospheric, mature sophisticated style, premium quality` |
| 진장(晋江) | 분홍·보라·연파랑·따뜻한 흰색 등 부드러운 색조와 섬세한 이목구비. 중앙 대칭 구도에 꽃잎·빛망울·비단·보석 장식. 제목은 우아한 행서체나 가는 둥근 글꼴 | `dreamy ethereal aesthetic, soft pastel tones, elegant romantic, delicate beauty, flower petals and bokeh` |
| 즈후 옌옌(知乎盐言) | 회색·파랑·흰색 또는 어두운 색의 미니멀한 화면과 넓은 여백. 장면·사물·추상적 이미지로 분위기를 만들고 인물 묘사는 적음. 제목은 현대적이고 간결한 산세리프체로 독립 영화 포스터에 가까움 | `minimalist literary style, clean composition with negative space, subtle moody atmosphere, independent film poster aesthetic` |
| 치마오(七猫) | 높은 채도와 강한 인상, 화려한 의상. 불꽃·번개·영력 효과로 포스터 느낌 강화. 제목은 크고 빛나며 정보 밀도가 높음 | `striking high-impact design, vivid dramatic colors, spectacular visual effects, attention-grabbing poster style` |
| 츠웨이마오(刺猬猫) | 밝고 선이 뚜렷한 일본 애니메이션풍 삽화. SD 요소와 만화풍 손글씨 제목을 더해 가볍고 활기찬 느낌 | `anime illustration style, vibrant colorful, detailed character art, Japanese light novel aesthetic` |

표에 없는 플랫폼은 플랫폼 키워드 문자열을 추가하지 않습니다.

---

## 장르 추론 규칙

장르 유형이 없거나 스타일 라이브러리와 맞지 않을 때만 사용합니다. 제목과 필요한 경우 소개를 단어 단위로 대조하며 한 글자씩 대조하지 않습니다. 아래 중국어는 원문 제목을 판별하는 검색 키워드이므로 유지합니다.

| 키워드 | 장르 |
|:-------|:-----|
| 修仙、修真、仙尊、仙帝、仙门、宗门、剑仙、剑尊、剑道、帝尊、神帝、灵根、飞升、渡劫、长生、玄幻 | 현환 / 선협 |
| 都市、校园、兵王、神医、战神、赘婿、神豪、首富、学霸 | 도시물 |
| 王妃、皇后、贵妃、太子妃、嫡女、庶女、侯府、王府、宫斗、宅斗、公主、娘娘 | 고전 로맨스 / 궁중 암투 |
| 总裁、霸总、豪门、契约、替嫁、甜宠、娇妻、萌宝、闪婚、离婚、前夫、追妻 | 현대 로맨스 / 달콤한 로맨스 |
| 命案、凶案、诡案、刑侦、法医、侦探、悬疑、推理、密室、连环 | 서스펜스 / 추리 |
| 星际、末世、末日、丧尸、天灾、机甲、赛博、废土、进化 | SF / 아포칼립스 |
| 魔法、魔王、巨龙、龙族、骑士、精灵、领主、异世界 | 서양 판타지 |
| 三国、大明、大唐、大宋、大秦、战场、将军、谋士 | 역사 / 군사 |
| 鬼怪、捉鬼、诡异、僵尸、阴阳、风水、盗墓、诅咒、冥婚 | 초자연 / 공포 |
| 二次元、动漫、猫娘、萌娘、转生 | 라이트노벨 / 애니메이션풍 |

여러 장르가 일치하면 다음 순서에서 첫 번째를 선택합니다. 현환 / 선협 > 서양 판타지 > 고전 로맨스 / 궁중 암투 > 현대 로맨스 / 달콤한 로맨스 > 도시물 > 서스펜스 / 추리 > SF / 아포칼립스 > 역사 / 군사 > 초자연 / 공포 > 라이트노벨 / 애니메이션풍. 일치하는 장르가 없으면 우선 「도시물」을 사용하고 작가에게 시안을 제시할 때 알립니다.

---

## 구도 변형

| 구도 | 키워드 | 적합한 경우 |
|:-----|:-------|:-----|
| 인물 클로즈업 + 배경 | `close-up portrait, face filling upper half` | 모든 장르에 사용 가능, 인물 강조 |
| 전신 + 역동적 자세 | `full body shot, dynamic pose` | 현환·도시물·서양 판타지. 의상과 동작 표현 |
| 배경 / 분위기만 | `no human figure, landscape composition` | 서스펜스·SF·역사, 즈후 옌옌 |
| 두 인물 | `two figures facing each other` | 현대·고전 로맨스 등 |

---

## 조명 효과

| 조명 | 키워드 | 느낌 |
|------|--------|------|
| 신성 | `dramatic golden light from above` | 신성함 |
| 신비 | `cold moonlight from the left casting long shadows` | 신비로움 |
| 따뜻함 | `warm sunset glow backlighting the figure` | 따뜻한 느낌 |
| SF | `neon blue and purple lights from below` | SF 분위기 |

---

## 스타일 라이브러리

각 항목의 제목 글꼴과 필명 글꼴을 템플릿의 텍스트 층에 그대로 넣습니다. 영어 키워드는 이미지 생성 모델에 전달할 디자인 지시이므로 원문을 유지합니다.

### 현환 / 선협

**태그**：`xianxia Chinese fantasy art style, ethereal atmosphere`
**색상**：청색 + 금색 + 짙은 검정. 차가운 색을 중심으로 금색·따뜻한 광원 강조
**인물**：남성: 긴 머리를 관으로 묶거나 풀어 내리고 검·법기를 듦. 옷자락이 날림 | 여성: 하늘거리는 선녀복, 영수 동행, 연꽃 장식
**배경**：운해, 선산, 옛 누각, 영력 빛 효과
**조명**：`divine golden light rays, mystical mist, spiritual energy glow`
**제목 글꼴**：`bold golden brush calligraphy with metallic glow and sharp strokes`
**필명 글꼴**：`small refined white serif text with faint golden glow, flanked by delicate cloud-scroll ornaments on both sides, resting on a thin horizontal gold line`
**예시**(치뎬, 2:3)：
```
Chinese web novel cover design, polished refined illustration, detailed cinematic composition, epic atmospheric, mature sophisticated style, premium quality.
Title text '剑道独尊' at top center in bold golden brush calligraphy with metallic glow and sharp strokes.
Author name '青椒炒肉' at bottom center in small refined white serif text with faint golden glow, flanked by delicate cloud-scroll ornaments, resting on a thin horizontal gold line.
xianxia Chinese fantasy art style, ethereal atmosphere. full body shot, dynamic pose.
A young swordsman in flowing white robes standing on a mountain peak,
holding a glowing blue spirit sword, long black hair flowing in the wind.
Ethereal clouds swirling below, dark misty mountain peaks in background.
Color palette: deep blue, gold, white, black. Dramatic golden divine light from above, spiritual energy particles.
Professional book cover, high detail digital painting, portrait 2:3 ratio, keep title and author name inside the central safe area away from edges (inner ~85%), no watermark
```

### 도시물

**태그**：`modern urban contemporary style, clean cinematic composition`
**색상**：짙은 파랑 + 회색 + 금색. 야경은 네온, 황혼은 따뜻한 주황으로 강조
**인물**：남성: 정장·캐주얼 차림, 능숙한 인상과 뚜렷한 윤곽 | 여성: 세련된 옷차림과 자신감 있는 표정
**배경**：도시 스카이라인, 고급 사무실, 캠퍼스, 네온 거리
**조명**：`sharp city lights, sunset glow reflecting on glass buildings, neon rim light`
**제목 글꼴**：`modern bold sans-serif with metallic silver finish`
**필명 글꼴**：`small clean white modern text with subtle drop shadow, positioned above a thin silver horizontal divider line`

### 고전 로맨스 / 궁중 암투

**태그**：`ancient Chinese romance palace drama, elegant classical beauty`
**색상**：선명한 빨강 + 금색 + 먹색. 호화롭고 묵직한 느낌
**인물**：여성: 화려한 예복, 봉관·비녀, 정교한 화장 | 남성: 황제·장군의 위엄 또는 온화함
**배경**：궁전, 정원, 붉은 담장, 구슬발, 병풍, 등롱
**조명**：`warm lantern light, golden candle glow, silk fabric shimmering`
**제목 글꼴**：`elegant golden traditional Kai script with ornate decoration`
**필명 글꼴**：`small elegant dark red traditional text inside a thin golden rectangular border frame with corner decorations`

### 현대 로맨스 / 달콤한 로맨스

**태그**：`modern romance cover art, soft dreamy warm atmosphere`
**색상**：분홍 + 따뜻한 흰색 + 옅은 금색. 따뜻하고 부드러움
**인물**：두 인물 구도를 중심으로 달콤한 교감(포옹·눈맞춤·손잡기)
**배경**：카페, 정원, 아늑한 실내, 노을 진 해변
**조명**：`soft warm backlighting, dreamy bokeh, gentle sunset glow`
**제목 글꼴**：`soft rounded handwritten style in white with pink glow`
**필명 글꼴**：`small soft pink-white handwritten text with a tiny heart motif on the left side, light sparkle effect`

### 서스펜스 / 추리

**태그**：`dark mystery thriller, noir atmosphere, high contrast shadows`
**색상**：검정 + 짙은 회색 + 어두운 파랑. 핏빛 빨강·차가운 흰색으로 강조
**인물**：실루엣·반쯤 가린 얼굴·뒷모습. 침착하거나 긴장한 모습
**배경**：비 오는 밤 거리, 낡은 건물, 밀실, 어두운 골목
**조명**：`dramatic chiaroscuro, single spotlight, rain-slicked reflections`
**제목 글꼴**：`distorted bold cracked letters in blood red`
**필명 글꼴**：`small pale grey text with slight blur effect, almost hidden in the shadows, a thin cracked line underneath`

### SF / 아포칼립스

**태그**：`sci-fi cyberpunk, futuristic technology, post-apocalyptic`
**색상**：짙은 파랑 + 검정 + 은색. 네온 파랑·전자 보라·에너지 초록으로 강조
**인물**：메카 슈트·전술복·실험실 가운, SF 무기·홀로그램 인터페이스
**배경**：우주, 폐허 도시, 실험실, 우주 정거장
**조명**：`holographic blue glow, neon rim lighting, energy arcs`
**제목 글꼴**：`neon glowing futuristic font in electric blue`
**필명 글꼴**：`small crisp white monospace text with subtle cyan scanline overlay, flanked by small geometric brackets`

### 서양 판타지

**태그**：`western high fantasy, epic medieval atmosphere`
**색상**：짙은 파랑 + 어두운 금색 + 은백색. 불꽃 빨강·마법 보라로 강조
**인물**：기사 갑옷·마법사 로브·레인저 가죽 갑옷. 용·그리핀 동행
**배경**：성, 용의 둥지, 마법진, 광활한 들판
**조명**：`magic spell glow, dramatic stormy sky, firelight from torches`
**제목 글꼴**：`metallic embossed fantasy lettering with glow effect`
**필명 글꼴**：`small bronze medieval script text with aged parchment texture, enclosed in a small decorative shield or banner shape`

### 역사 / 군사

**태그**：`historical Chinese war epic, grand battlefield panorama`
**색상**：철회색 + 어두운 빨강 + 황토색. 황금 갑옷의 광택·봉화의 주황으로 강조
**인물**：장군 갑옷·책사 장포, 무기를 든 모습
**배경**：전장, 성벽, 군영, 봉화
**조명**：`dramatic battlefield firelight, smoke-filled sky, sunset over war`
**제목 글꼴**：`heavy stone-carved seal script in deep red`
**필명 글꼴**：`small dignified white Song typeface text above a double horizontal line in dark red`

### 초자연 / 공포

**태그**：`Chinese supernatural horror, eerie ghostly atmosphere`
**색상**：먹색 + 음산한 초록 + 어두운 빨강. 종이 흰색·촛불 노랑으로 강조
**인물**：도사 복장 또는 기이한 사건에 휘말린 평범한 사람, 귀신 그림자·종이 인형·강시
**배경**：묘지, 오래된 사당, 어두운 골목, 관
**조명**：`eerie green glow, flickering candlelight, cold ghostly luminescence`
**제목 글꼴**：`eerie dripping handwritten font in sickly green`
**필명 글꼴**：`small faded grey-green text slightly tilted, with a thin dripping ink line above`

### 라이트노벨 / 애니메이션풍

**태그**：`anime light novel cover, vibrant colorful moe style`
**색상**：밝고 다양한 색상, 별빛·꽃잎으로 강조
**인물**：SD·귀여운 캐릭터, 고양이 귀·날개 등 귀여운 특징
**배경**：판타지 세계, 캠퍼스, 이세계, 별이 빛나는 하늘
**조명**：`sparkly star effects, magical particle effects, soft luminous glow`
**제목 글꼴**：`colorful cartoon outlined bubbly font`
**필명 글꼴**：`small playful rounded white text with pastel color outline, tiny star decorations on both sides`
