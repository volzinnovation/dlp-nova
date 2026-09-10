#ifndef DLP_NATIVE_WINDOWS_H
#define DLP_NATIVE_WINDOWS_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* ABI 1: bounded event-time state. Byte strings are opaque, copied on input.
 * One worker serializes each store. No exception crosses the ABI; int functions
 * return 0 success/-1 failure. Error codes: 1 invalid, 2 resource, 3 late,
 * 4 revision, 5 replay/context gap, 6 malformed checkpoint, 7 allocation/internal.
 * Clocks are signed microseconds, intervals [end-width,end); subtraction uses
 * extended precision. Revisions/offsets fit nonnegative int64. Key equality and
 * payload equality are byte equality; IDs use byte lexicographic tie ordering.
 * The row field is an opaque payload. Change identity is (id,time,key,row),
 * excluding revision: distinct event IDs never collapse even with equal payload.
 * Successful mutations return a bounded publication; free it after consumption.
 * Exports pin immutable records and survive subsequent mutations/store close.
 * At most 8 exports/publications may be live per store; 128 source offsets.
 * Byte budgets conservatively charge string bytes*4 + fixed record overhead;
 * transactional copying/export handles consume additional bounded memory.
 */
typedef struct dlp_window_store dlp_window_store;
typedef struct dlp_window_rows dlp_window_rows;
typedef struct dlp_window_change dlp_window_change;
typedef struct dlp_window_bytes {
    const void *data;
    size_t size;
} dlp_window_bytes;
typedef struct dlp_window_event {
    dlp_window_bytes id, key, row;
    int64_t time, revision;
} dlp_window_event;
typedef struct dlp_window_config {
    int64_t width, lateness, end, watermark;
    uint64_t max_events, max_bytes, max_keys;
    uint32_t predecessors, allow_gaps;
} dlp_window_config;
typedef struct dlp_window_info {
    uint64_t revision, events, tombstones, bytes, sources;
    int64_t end, watermark;
} dlp_window_info;
uint32_t dlp_windows_abi(void);
const char *dlp_windows_error(void);
int32_t dlp_windows_error_code(void);
int dlp_windows_new(const dlp_window_config *, dlp_window_bytes context, dlp_window_store **);
void dlp_windows_free(dlp_window_store *);
int dlp_windows_info(dlp_window_store *, dlp_window_info *);
int dlp_windows_config(dlp_window_store *, dlp_window_config *, dlp_window_bytes *context);
int dlp_windows_event(dlp_window_store *, dlp_window_bytes id, dlp_window_event *, int *found);
int dlp_windows_predecessor(dlp_window_store *, dlp_window_bytes id, dlp_window_event *,
                            int *found);
int dlp_windows_offset(dlp_window_store *, size_t index, dlp_window_bytes *source, int64_t *offset);
int dlp_windows_upsert(dlp_window_store *, const dlp_window_event *, dlp_window_bytes source,
                       int64_t offset, dlp_window_change **);
int dlp_windows_remove(dlp_window_store *, dlp_window_bytes id, int64_t revision,
                       dlp_window_change **);
int dlp_windows_advance(dlp_window_store *, int64_t end, int64_t watermark, dlp_window_change **);
int dlp_windows_forget(dlp_window_store *, dlp_window_bytes key, dlp_window_change **);
/* mode 0 active, 1 active+predecessor, 2 all retained records. */
int dlp_windows_rows(dlp_window_store *, uint32_t mode, dlp_window_rows **);
int dlp_windows_next(dlp_window_rows *, dlp_window_event *, size_t capacity, size_t *count,
                     int *done);
void dlp_windows_rows_free(dlp_window_rows *);
/* mode 0 active added, 1 removed, 2 history added, 3 removed,
 * 4 retained records added, 5 removed (these include revision-only corrections).
 * Returned event pointers remain borrowed until export/publication free. */
int dlp_windows_change_next(dlp_window_change *, uint32_t mode, dlp_window_event *, size_t capacity,
                            size_t *count, int *done);
int dlp_windows_change_revision(dlp_window_change *, uint64_t *);
void dlp_windows_change_free(dlp_window_change *);
/* Deterministic little-endian framed checkpoint v1, CRC32 for accidental
 * corruption only (not authentication). NULL/capacity0 is a sizing call.
 * Restore checks host caps before allocation and publishes only valid state.
 * expected_context may be NULL to accept the stored opaque context bytes. */
int dlp_windows_checkpoint(dlp_window_store *, void *output, size_t capacity, size_t *size);
int dlp_windows_restore(const void *, size_t size, uint64_t max_checkpoint_bytes,
                        uint64_t max_events, uint64_t max_bytes, uint64_t max_keys,
                        const dlp_window_bytes *expected_context, dlp_window_store **);
#ifdef __cplusplus
}
#endif
#endif
