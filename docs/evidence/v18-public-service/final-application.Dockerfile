# The base is the successful standard 1.8 api image from backend-build.log.
# Dependency lock and package versions are unchanged by this final source fix.
FROM qinggui-assessment-base:1.8
COPY backend ./backend
COPY scripts ./scripts
COPY evaluations ./evaluations
