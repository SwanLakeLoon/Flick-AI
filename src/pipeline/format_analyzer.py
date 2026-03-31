# Standard issue passenger plate mappings based on latest state conventions
# Format rules: 'L' = Letter, 'N' = Number
# Vanity plates, obscure specials, and highly randomized layouts will not match these strong heuristics

FORMAT_TO_STATES = {
    # 3 Letters, 4 Numbers (ABC 1234)
    "LLLNNNN": ["WI", "MI", "NY", "OH", "PA", "TX", "VA", "WA", "GA", "NC"],
    
    # 3 Letters, 3 Numbers (ABC 123)
    "LLLNNN": ["MN", "IA", "ND", "AK", "HI", "IN", "LA", "ME", "MS", "NE", "NM", "OK", "OR", "SC", "VT"],
    
    # 1 Number, 3 Letters, 3 Numbers (1ABC234)
    "NLLLNNN": ["CA"],
    
    # 2 Letters, 5 Numbers (AB 12345)
    "LLNNNNN": ["IL", "CT"],
    
    # 2 Letters, 4 Numbers (AB 1234)
    "LLNNNN": ["RI", "DC"],
    
    # 3 Letters, 1 Letter, 2 Numbers (ABC D12)
    "LLLLNN": ["FL", "CO"],
    
    # 3 Letters, 1 Number, 2 Letters (ABC 1DE)
    "LLLNNL": ["AR"],
    
    # 1 Letter, 2 Numbers, 3 Letters (A12 BCD)
    "LNNLLL": ["NJ"],
    
    # 3 Numbers, 3 Letters (123 ABC)
    "NNNLLL": ["KS"],
    
    # 1 Number, 2 Letters, 4 Numbers (1AB 2345)
    "NLLNNNN": ["MD"],
    
    # 6 Numbers (123456)
    "NNNNNN": ["DE", "MA"],
    
    # 7 Numbers (1234567)
    "NNNNNNN": ["NH"]
}

VALID_US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", 
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", 
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", 
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", 
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC"
}

def analyze_plate_format(plate: str) -> str:
    """Converts a raw plate string into its abstract L/N format representation."""
    clean_plate = plate.upper().replace(" ", "").replace("-", "")
    abstract = ""
    for char in clean_plate:
        if char.isalpha():
            abstract += "L"
        elif char.isdigit():
            abstract += "N"
        else:
            abstract += "?"
    return abstract

def get_probable_states(plate: str) -> list[str]:
    """
    Evaluates an alphanumeric string against the national format database.
    Returns a list of highly probable states (e.g. ['WI', 'MI', 'OH'])
    If the format is too short, erratic, or unknown, returns an empty list.
    """
    if len(plate) < 4:
        return []
        
    abstract_format = analyze_plate_format(plate)
    return FORMAT_TO_STATES.get(abstract_format, [])

