#!/bin/bash
# Build one board of dingoFW as a host shared object. Usage: build.sh <board> <outdir>
set -e
B=$1; OUT=$2; UNIT=$3; N=$B; [ -n "$UNIT" ] && N=${B}_unit$UNIT; FW=$(cd "$(dirname "$0")/.." && pwd); mkdir -p $OUT/obj_$N
SRC="boards/$B/port.cpp boards/$B/msg.cpp boards/$B/hw_devices.cpp comms/can.cpp comms/infomsg.cpp comms/mailbox.cpp comms/request_msg.cpp
core/config.cpp core/config_ext.cpp core/config_handler.cpp core/error.cpp core/led.cpp core/param_protocol.cpp core/param_registry.cpp
core/status.cpp core/device.cpp core/sleep.cpp core/safety.cpp functions/can_input.cpp functions/can_outputs.cpp functions/condition.cpp functions/counter.cpp
functions/flasher.cpp functions/input.cpp functions/math_block.cpp functions/timer.cpp functions/virtual_input.cpp functions/profet.cpp functions/pwm.cpp functions/digital_input.cpp
functions/starter.cpp functions/wiper/wiper_digin.cpp functions/wiper/wiper_intin.cpp functions/wiper/wiper_mixin.cpp functions/wiper/wiper.cpp
functions/keypad/blink/blink_button.cpp functions/keypad/blink/blink_dial.cpp functions/keypad/blink/blink_analog_input.cpp
functions/keypad/blink/blink_keypad.cpp functions/keypad/grayhill/grayhill_button.cpp functions/keypad/grayhill/grayhill_keypad.cpp
functions/keypad/keypad_button.cpp functions/keypad/keypad.cpp utils/crc.cpp utils/dbc.cpp sim/sim_core.cpp"
grep -q "functions/analog_input.cpp" $FW/boards/$B/board.mk && SRC="$SRC functions/analog_input.cpp"
INC="-I$FW/sim/include -I$FW/boards/$B -I$FW -I$FW/core -I$FW/comms -I$FW/functions -I$FW/functions/wiper -I$FW/functions/keypad
-I$FW/functions/keypad/blink -I$FW/functions/keypad/grayhill -I$FW/utils -I$FW/hardware"
[ -n "$UNIT" ] && DEF="-DPDM_UNIT=$UNIT"
FLAGS="$DEF -std=c++20 -O1 -g -fPIC -fsingle-precision-constant -fno-exceptions -fno-threadsafe-statics -fvisibility=hidden -Wall -Wno-register -Wno-unused -Wno-deprecated"
OBJS=""
for s in $SRC; do o=$OUT/obj_$N/$(echo $s | tr / _).o; g++ $FLAGS $INC -c $FW/$s -o $o & OBJS="$OBJS $o"; done; wait
g++ -shared -Wl,-Bsymbolic -o $OUT/$N.so $OBJS
echo built $OUT/$N.so
