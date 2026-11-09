# PARK에 기여하기 / Contributing

기여를 환영합니다! 작은 수정도 큰 도움이 됩니다. · Contributions of any size are welcome.

## 개발 환경

```bash
git clone https://github.com/j52367/park-patent.git
cd park-patent
pip install -e ".[dev,excel,learn,fulltext]"
pytest -q
park demo
```

## 특히 도움이 되는 기여

- **DB 내보내기 헤더:** KIPRIS 웹, WIPS, 기타 DB에서 내려받은 파일의 열 이름이 인식되지 않으면 `park/ingest.py`의 `HEADER_SYNONYMS`에 추가해 주세요. 가능하면 가상 데이터로 만든 테스트도 함께 보내 주세요.
- **KIPRIS API 확인 결과:** 새로 확인한 서비스, 파라미터, 응답 형식은 `docs/kipris-api-notes.md`에 날짜와 함께 적어 주세요.
- **출원인 이름 규칙:** 법인 표기 변형, 그룹 병합 규칙 (`park/normalize.py`).
- **스킬:** `skills/<이름>/SKILL.md`. 숫자는 `park` 도구로 세고, 판정에는 원문 인용을 다는 원칙(`skills/shared-references/principles.md`)을 따라 주세요.

## 규칙

- **실제 특허 데이터나 개인정보를 저장소에 넣지 마세요.** 테스트와 예시는 가상의 기업, 문헌, 번호로 만듭니다. KIPRIS에서 받은 데이터는 KIPRIS Plus 이용약관을 따릅니다.
- **API 키를 커밋하지 마세요.** 키는 `.env`(git 제외)에만 둡니다.
- 새 기능에는 테스트를 붙여 주세요. CI는 Ubuntu와 Windows, Python 3.10과 3.13에서 돕니다.
- 집계 규칙이나 판정 기준을 바꾸면 `docs/DESIGN.md`의 변경 내역에 이유를 적어 주세요.

## Reporting issues

Please include the command you ran, the error output, and — if it is about an import — the column headers of the file (not its data).
