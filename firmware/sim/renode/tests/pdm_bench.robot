*** Settings ***
Documentation     custom-pdm bench: the three real firmware binaries (board A unit 1, board A unit 2, board B) in Renode
...               on one CAN hub. Repeats the checks of firmware/sim/s1_system.py. The tests share one emulation and
...               run in file order; a failed test can make later ones fail.
Suite Setup       Start Suite
Suite Teardown    Teardown
# renode-test adds "Reset Emulation" around every test that has no setup / teardown of its own
Test Setup        No Operation
Test Teardown     No Operation
Resource          ${RENODEKEYWORDS}
Library           ${CURDIR}/pdm_bench.py    ${SIMDIR}    ${BENCH_RESC}

*** Keywords ***
Start Suite
    Setup
    Start Bench

*** Test Cases ***
Three Fresh Boards Come Up At 1 Mbit/s And Each Answers Alone On Its Own Built-in ID
    Fresh Boards Answer On Their Own Ids

Fresh Boards Run Without Fatal Error And Report The Battery Voltage
    No Board Is In Fatal Error

Fresh Boards Wrote Their Default Config To The FRAM
    Fresh Boards Wrote Default Config To Fram

After A Power Cycle All Three Still Run At 1 Mbit/s On Their Own IDs With The Saved Config
    Power Cycle Keeps Ids And Config

Factory Defaults: Fan Output A2 OUT2 Always On, Temperature Limits 55 / 80 / 6 C, Only The Fan Exempt From Critical
    Factory Defaults Fan Output And Temperature Limits

Config As One 24-Output PDM Is Written Over CAN And Saved To FRAM
    Configure As One Pdm And Save

Walking One ECU Bit Through 23 Outputs Switches Exactly That Output And The Status Agrees
    Walking One Ecu Bit Through 23 Outputs

Cross-board Rule: An Input On Board B Switches Output 5 On Board A1 And Releases It
    Cross Board Rule Switches And Releases

One Total-current Number From Three Boards
    One Total Current Number From Three Boards

Link Loss, ECU Quiet, Outputs On: Hold Stays On, Off Drops After The Time-out, On Stays On, All Recover
    Ecu Goes Quiet While Outputs Are On

Link Loss, ECU Quiet, Outputs Off: Hold Stays Off, On Turns On After The Time-out, All Recover
    Ecu Goes Quiet While Outputs Are Off

Board A1 Unplugged: Only A1 Applies Its Policies, Its Status Goes Stale, Board B Carries On
    Board A1 Unplugged From Can

Board B Unplugged: Only B Applies Its Policies, Its Status Goes Stale, Board A1 Carries On
    Board B Unplugged From Can

Cross-board Rule Drops When Board B Falls Off The Bus And Returns With It
    Cross Board Rule Drops When Its Source Board Is Lost

Board Restarts With No ECU On The Bus: Hold Off, Off Off, On On, Then Follows The ECU
    Board Restarts With No Ecu On The Bus

Board Restarts While The ECU Is Talking: Outputs Come Back, Saved Config Survives
    Board Restarts While The Ecu Is Talking

Overcurrent: Three Tries One Second Apart, Then Fault Until A Power Cycle
    Overcurrent Retries Three Times Then Latches Fault

Board Temperature From The I2C Sensor Reaches The Status Frame And The Over-temperature State
    Board Temperature Reaches The Status Frame

Board And STM32 Die Temperatures Reach CAN x10, Each Tracking Its Own Set Value
    Board And Die Temperatures Reach Can

Above Warn: Over-temperature State And Error Message, Outputs Unchanged
    Above Warn Outputs Unchanged

At Critical: All Outputs Off, No Chatter, Back By Themselves Below Critical Minus Hysteresis
    At Critical All Off Then Recovers Below Critical Minus Hysteresis

Manual Setup: ID And Bit Rate Changed Over CAN, Saved, Kept After A Restart
    Manual Id And Bit Rate Change Survives A Restart

Sleep: Every PROFET IN / DEN / DSEL Line Low, LEDs Off, MCP9808 Alert Off And In Shutdown
    Sleep Drives Every Profet Line Low And Shuts The Sensor Down

Wake-up: DEN High Again, MCP9808 Back To Continuous, No Stale Pre-sleep Reading Used
    Wake Up Restores Den And The Sensor Without A Stale Reading

MCP9808 Read Failures: Critical Held, Fault Message After 4 In A Row, Recovers When Reads Return
    Sensor Read Failures Keep Critical And Send A Fault Message
