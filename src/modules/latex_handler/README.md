`latex_text_builder`는 본문(mainbody) 앞뒤에 접두 문자열과 접미 문자열을 붙이는 역할만 한다. 접두 문자열에는 LaTeX preamble 코드가, 접미 문자열에는 참고문헌(reference) 생성 코드가 들어 있다.


`latex_figure_builder`는 mainbody.tex에서 세 개의 장(chapter)을 선택한다. 이 세 장은 본문 내 인용 수가 가장 많은 상위 3개이며, 이를 구조 그림(structure figure)으로 그린다. latex_figure_builder는 구조 그림의 LaTeX 코드를 생성해 survey.tex에 삽입한다.

`latex_sheet_builder`는 인용 수가 가장 많은 section을 선택한 뒤, 해당 section을 기반으로 표(sheet)를 생성한다.
