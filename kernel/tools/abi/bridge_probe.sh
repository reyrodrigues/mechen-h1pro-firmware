set -e
cd /obj
cmd=$(sed -n 's/^cmd_drivers\/misc\/mediatek\/connectivity\/common\/wmt_build_in_adapter.o := //p' drivers/misc/mediatek/connectivity/common/.wmt_build_in_adapter.o.cmd)
cmd=$(echo "$cmd" | sed -e 's/ -c / -E -D__GENKSYMS__ /' -e 's/-o drivers[^ ]*wmt_build_in_adapter.o/-o \/tmp\/b.i/')
eval "$cmd"
grep -n -B2 -A6 "^struct wmt_platform_bridge {" /tmp/b.i | head -20
try(){ sed -e "$2" /tmp/b.i > /tmp/p.i; printf '%-24s ' "$1"; /obj/scripts/genksyms/genksyms < /tmp/p.i | grep -oE "__crc_wmt_export_platform_bridge_register = 0x[0-9a-f]+" || echo none; }
try base 's/x/x/'
try void_cbs 's/^typedef int (\*wmt_bridge_\(thermal_query\|trigger_assert\)_cb)/typedef void (*wmt_bridge_\1_cb)/'
try long_thermal 's/^typedef int (\*wmt_bridge_thermal_query_cb)/typedef long (*wmt_bridge_thermal_query_cb)/'
