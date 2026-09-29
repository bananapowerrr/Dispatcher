def divide(a, b):
    return a / b

def test_divide():
    assert divide(10, 2) == 5
    assert divide(7, 3) == 7 / 3
    assert divide(0, 1) == 0
    try:
        divide(1, 0)
    except ZeroDivisionError:
        pass
    else:
        assert False, "Expected ZeroDivisionError"
