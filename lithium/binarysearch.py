def binarySearchForLast():
    low = 0 # all removed
    high = numParts # none removed
    
    # We want to end with x == low == high such that
    # interestingWithoutS(x) is True
    # interestingWithoutS(x + 1) is False or meaningless
    
    while low < high:
        mid = ((low + high) // 2)
        #assert(low <= mid < high)
        if interestingWithoutS(mid):
            high = mid
            
        
        
        
    
    


