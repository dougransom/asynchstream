use std::fs::OpenOptions;

/// Strongly typed representation of file access modes.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct FileMode {
    pub readable: bool,
    pub writable: bool,
    pub append: bool,
    pub truncate: bool,
    pub binary: bool,
}

impl FileMode {
    /// Parse raw Python mode string (e.g. "r", "w+b", "a") into a strongly typed FileMode.
    pub fn parse(mode: &str) -> Self {
        let mode_str = if mode.is_empty() { "rb" } else { mode };
        let is_write = mode_str.contains('w') || mode_str.contains('a') || mode_str.contains('+');
        let is_read = mode_str.contains('r')
            || mode_str.contains('+')
            || (!mode_str.contains('w') && !mode_str.contains('a'));

        FileMode {
            readable: is_read,
            writable: is_write,
            append: mode_str.contains('a'),
            truncate: mode_str.contains('w'),
            binary: mode_str.contains('b'),
        }
    }

    /// Configure std::fs::OpenOptions flags according to this FileMode.
    pub fn configure_open_options(&self, options: &mut OpenOptions) {
        if self.writable {
            if self.truncate {
                options.write(true).create(true).truncate(true);
            } else if self.append {
                options.write(true).create(true).append(true);
            } else {
                options.write(true).create(true);
            }
            if self.readable {
                options.read(true);
            }
        } else {
            options.read(true);
        }
    }
}
