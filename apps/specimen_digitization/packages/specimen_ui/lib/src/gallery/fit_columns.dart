/// The column widths the Fit page and the family fit sections share.
library;

/// Narrowest first. The four columns and their gutters come to 1380 dp and no
/// window in the system leaves a page that much, so one end of the row is
/// always off screen; the end worth losing is the wide one, which is the case
/// every family page already reviews. Read left to right this is a control
/// recovering as it is given room rather than degrading as it is starved,
/// which says the same thing in the other direction.
const List<double> fitColumns = <double>[200, 280, 360, 480];
