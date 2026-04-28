// Shared display rules for dbo.Contract.Status.
//
// The DB column today is just 'active' for everything; expired and
// expiring_soon are computed at display time from ExpirationDate so the badge
// actually fires. No DB writes happen here. If a future ingest job ever writes
// literal 'expired' / 'expiring_soon' into Status, displayStatus passes them
// through unchanged.
export const EXPIRING_SOON_DAYS = 90;
export const STATUS_BADGE = {
    active: "badge-ok",
    expiring_soon: "badge-warn",
    expired: "badge-danger",
};
export function displayStatus(status, expirationDate) {
    const s = status ?? "";
    if (s !== "active" || !expirationDate)
        return s;
    const exp = new Date(expirationDate).getTime();
    if (Number.isNaN(exp))
        return s;
    const days = Math.ceil((exp - Date.now()) / 86_400_000);
    if (days < 0)
        return "expired";
    if (days <= EXPIRING_SOON_DAYS)
        return "expiring_soon";
    return s;
}
