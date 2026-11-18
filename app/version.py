"""앱 코드 버전. 릴리스할 때 올린다 (release.ps1 이 읽음). 형식: 주.부.수 (예: 1.0.0)"""
VERSION = "1.1.5"
# 이 코드를 돌리는 데 필요한 최소 exe(로더) 버전. 새 라이브러리를 쓰는 등 exe 를 다시 만들어야 하면
# launcher/launcher.py 의 LOADER_VERSION 과 함께 올린다 → 예전 exe 사용자에게 '새 설치 파일 필요' 안내
MIN_LOADER = 1
