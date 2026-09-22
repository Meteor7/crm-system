function ConvertTo-CrmHttpFormValue {
    param([AllowNull()][object]$Value)
    # Invoke-RestMethod deserializes ISO JSON timestamps into DateTime values.
    # Form and multipart encoders must not use culture-dependent ToString().
    if ($Value -is [datetime] -or $Value -is [datetimeoffset]) {
        return $Value.ToString('o', [Globalization.CultureInfo]::InvariantCulture)
    }
    return ,$Value
}
