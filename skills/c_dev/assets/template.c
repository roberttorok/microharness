#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char **argv)
{
    if (argc < 2) {
        fprintf(stderr, "usage: %s <name>\n", argv[0]);
        return EXIT_FAILURE;
    }

    printf("Hello, %s!\n", argv[1]);
    return EXIT_SUCCESS;
}
