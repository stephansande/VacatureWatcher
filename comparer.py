from difflib import unified_diff



def compare_content(
    old_content,
    new_content
):
    """
    Vergelijkt twee teksten
    en geeft verschillen terug.
    """


    if not old_content:

        return {
            "changed": True,
            "added": new_content,
            "removed": ""
        }



    if old_content == new_content:

        return {
            "changed": False,
            "added": "",
            "removed": ""
        }



    old_lines = (
        old_content
        .splitlines()
    )

    new_lines = (
        new_content
        .splitlines()
    )


    diff = list(
        unified_diff(
            old_lines,
            new_lines,
            lineterm=""
        )
    )


    added = []
    removed = []


    for line in diff:

        if line.startswith("+"):

            added.append(
                line[1:]
            )


        elif line.startswith("-"):

            removed.append(
                line[1:]
            )



    return {

        "changed": True,

        "added":
            "\n".join(
                added
            ),

        "removed":
            "\n".join(
                removed
            )

    }