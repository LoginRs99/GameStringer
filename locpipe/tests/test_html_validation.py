import pytest
from locpipe.validators.html_tags import check_html_tags

def test_html_tag_cases():
    cases = [
        # PASS CASES
        ("Press <b>Start</b>", "Nyomd meg a <b>Start</b> gombot", True),
        ("Info<br>More info", "Infó<br>Több infó", True),
        ("<color=red>HP</color>", "<color=piros>Élet</color>", True),
        ('<a href="en.hu">Link</a>', '<a href="hu.hu">Link</a>', True),
        ("I like <i>apples</i> and <b>pears</b>.", "Szeretem a <b>körtét</b> és az <i>almát</i>.", True),
        
        # REJECT CASES
        ("<b>Bold</b>", "Bold", False),
        ("<b>Bold</b>", "<b>Bold", False),
        ("<color=red>HP</color>", "HP</color>", False),
        ("Text", "<b>Text</b>", False),
        ("Press <icon=1> or <icon=2>", "Press <icon=1>", False),
        
        # EDGE CASES PASS
        ("10 < 20", "10 < 20", True),
        ("escaped &lt;b&gt;", "escaped &lt;b&gt;", True),
        ("< self-closing >", "< self-closing >", True),
        ("<b><i>BoldItalic</i></b>", "<i><b>FélkövérDőlt</b></i>", True),
        
        # EDGE CASES REJECT
        ("It is <brilliant>", "Zseniális", False),
        ("<b>{0}</b>", "{0}", False),
    ]
    
    for i, (source, target, expected_pass) in enumerate(cases):
        issues = check_html_tags(source, target)
        passed = len(issues) == 0
        assert passed == expected_pass, f"Case {i} failed: {source} -> {target}, expected pass={expected_pass}, got issues={issues}"
