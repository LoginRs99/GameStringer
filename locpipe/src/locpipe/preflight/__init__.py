"""Pre-run automation: font/glyph preflight and run-safety hardening
(TM snapshot, orphaned-artifact sweep). Runs before pipeline.run()/
plan() from cli.py's cmd_run/cmd_plan -- never imported by pipeline.py
itself, so locpipe's core stays free of any assumption about local
game-asset paths or agy's on-disk session layout.
"""
