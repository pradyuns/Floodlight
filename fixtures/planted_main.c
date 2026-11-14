/* Executable for every planted app: appends "<unix time> <own path>" to
 * ~/Library/Logs/planted-opens.log and exits, so a test can see which app Enter opened. */
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

int main(int argc, char **argv) {
    const char *home = getenv("HOME");
    if (home == NULL || argc < 1) return 1;
    char path[1024];
    snprintf(path, sizeof path, "%s/Library/Logs/planted-opens.log", home);
    FILE *log = fopen(path, "a");
    if (log == NULL) return 1;
    fprintf(log, "%ld %s\n", (long)time(NULL), argv[0]);
    fclose(log);
    return 0;
}
