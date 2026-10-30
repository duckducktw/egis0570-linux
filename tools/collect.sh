#!/bin/bash
# 指紋取樣：每次按一下，自動把影像歸檔到 ~/fp/data/<標籤>/<次數>/
D=/var/tmp/egisdump; OUT=~/fp/data; mkdir -p "$OUT"
round() {  # $1=標籤 $2=次數 $3=提示
  echo; echo "==== $3（共 $2 次）===="
  for i in $(seq 1 "$2"); do
    rm -f "$D"/*.pgm
    echo "[$1 $i/$2] 手指先離開感測器，看到 Place your finger 後按上去、按穩約 1 秒再放開"
    timeout 20 fprintd-verify 2>&1 | grep -iE "place|swipe|result" | tail -1
    n=$(ls "$D"/*.pgm 2>/dev/null | wc -l)
    if [ "$n" -gt 0 ]; then mkdir -p "$OUT/$1/$i"; mv "$D"/*.pgm "$OUT/$1/$i/"; echo "  ok（$n 張）"
    else echo "  沒抓到，這次不算"; fi
    sleep 1
  done
}
round A_same 10 "已註冊的那根手指，每次盡量按在『同一個位置』"
round A_move 10 "同一根手指，每次稍微換位置/角度"
round B_other 10 "換一根『沒註冊』的手指"
echo; echo "完成，資料在 $OUT"
