make -s -C /src O=/obj LOCALVERSION= KCFLAGS=-D__GENKSYMS__ lib/dynamic_debug.i >/dev/null 2>&1
I=/obj/lib/dynamic_debug.i
try(){ sed -e "$2" $I > /tmp/p.i; printf '%-28s ' "$1"; /obj/scripts/genksyms/genksyms < /tmp/p.i | grep -oE "__crc___dynamic_pr_debug = 0x[0-9a-f]+" || echo none; }
try base 's/x/x/'
try int 's/^void __dynamic_pr_debug(/int __dynamic_pr_debug(/'
try no_aligned 's/^} __attribute__((aligned(8)));/};/'
try int_no_aligned 's/^void __dynamic_pr_debug(/int __dynamic_pr_debug(/;s/^} __attribute__((aligned(8)));/};/'
try lineno_int 's/unsigned int lineno:18;/unsigned int lineno:18; unsigned int pad:6;/'
try flags_char 's/unsigned int flags:8;/unsigned char flags;/'
try int_flags_char 's/^void __dynamic_pr_debug(/int __dynamic_pr_debug(/;s/unsigned int flags:8;/unsigned char flags;/'
try static_key 's/unsigned int flags:8;/unsigned int flags:8; struct static_key key;/'
try int_static_key 's/^void __dynamic_pr_debug(/int __dynamic_pr_debug(/;s/unsigned int flags:8;/unsigned int flags:8; struct static_key key;/'
