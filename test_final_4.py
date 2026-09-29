def divide(a, b):
    return a / b

def test_divide():
    assert divide(10, 2) == 5
    assert divide(0, 1) == 0
    assert divide(5, 3) == 5 / 3
