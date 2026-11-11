#pragma once
#include "hal.h"
namespace chibios_rt
{
struct ThreadReference { thread_t *t = nullptr; };
struct BaseThread
{
    virtual void main() = 0;
    void setName(const char *) {}
    ThreadReference start(int prio);
    virtual ~BaseThread() {}
};
template <int N> struct BaseStaticThread : BaseThread {};
struct Mutex { void lock() {} void unlock() {} }; // cooperative scheduler: no pre-emption between sleeps
template <typename T, int N> struct Mailbox
{
    std::deque<T> q;
    msg_t post(T v, sysinterval_t) { if ((int)q.size() >= N) return MSG_TIMEOUT; q.push_back(v); return MSG_OK; }
    msg_t fetch(T *v, sysinterval_t) { if (q.empty()) return MSG_TIMEOUT; *v = q.front(); q.pop_front(); return MSG_OK; }
    size_t getUsedCountI() { return q.size(); }
};
}
