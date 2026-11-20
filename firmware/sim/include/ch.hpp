#pragma once
#include "hal.h"
namespace chibios_rt
{
struct ThreadReference { thread_t *t = nullptr; };
struct BaseThread
{
    virtual void main() = 0;
    void setName(const char *n) { chRegSetThreadName(n); }
    ThreadReference start(int prio);
    virtual ~BaseThread() {}
};
template <int N> struct BaseStaticThread : BaseThread {};
struct Mutex { void lock() {} void unlock() {} }; // cooperative scheduler: no pre-emption between sleeps (no holder sleeps)
template <typename T, int N> struct Mailbox
{
    std::deque<T> q; thread_t *waiter = nullptr;
    msg_t post(T v, sysinterval_t) { if ((int)q.size() >= N) return MSG_TIMEOUT; q.push_back(v); simWake(&waiter); return MSG_OK; }
    // blocks like chMBFetchTimeout: dingoFW development's CAN Tx thread waits here (100 ms time-out) instead of polling
    msg_t fetch(T *v, sysinterval_t timeout)
    {
        uint64_t deadline = simDeadline(timeout);
        while (q.empty())
            if (timeout == TIME_IMMEDIATE || !simWaitUntil(deadline, &waiter)) return MSG_TIMEOUT;
        *v = q.front(); q.pop_front(); return MSG_OK;
    }
    size_t getUsedCountI() { return q.size(); }
};
}
